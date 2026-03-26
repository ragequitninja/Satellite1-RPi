import logging
from typing import ClassVar, Literal, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from .board import BoardId
from .components.dac3101 import DAC3101, DAC3101Config
from .components.pcal6408a import PCAL6408A, PCAL6408AConfig
from .components.pcm5122 import PCM5122, PCM5122Config, PCM5122GPIOPin
from .components.power_delivery import PDContract, get_pd_contract
from .components.tas2780 import TAS2780, AudioCh, TAS2780Config

log = logging.getLogger(__name__)

Dac: TypeAlias = Literal["pcm5122", "tas2780", "auto"]
DacStr: TypeAlias = Literal["line-out", "speaker"]

PCM5122_JACK_SENSOR_PIN = 4
PCM5122_I2C_ADDR = 0x4D
TAS2780_I2C_ADDR = 0x3F
DAC3101_I2C_ADDR = 0x18
PCAL6408A_I2C_ADDR = 0x20


class DACConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    enabled: bool = True
    startup_volume: float = Field(
        0.5,
        ge=0.0,
        le=1.0,
        alias="startup-volume",
        description="Initial output level [0..1]",
    )
    startup_muted: bool = Field(
        False, alias="startup-muted", description="Un-mute DAC after initialization?"
    )
    restore_on_startup: bool = True


class LineOutDacConfig(DACConfig):
    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("line_out", "line-out", "pcm5122")


class LineOutDac(PCM5122):
    @classmethod
    def from_cfg(cls, config: DACConfig) -> Self:
        dac_config = PCM5122Config(
            enabled=config.enabled,
            i2c_bus=1,
            i2c_addr=PCM5122_I2C_ADDR,
            gpio=[
                PCM5122GPIOPin(
                    pin=PCM5122_JACK_SENSOR_PIN,
                    mode="in",
                    inverted=False,
                    name="line_out_jack_sensor",
                )
            ],
            volume=config.startup_volume,
            muted=config.startup_muted,
        )
        return cls(dac_config)

    @property
    def plugged_in(self) -> bool:
        return self.gpio_read(PCM5122_JACK_SENSOR_PIN)

    def report_status(self) -> str:
        return "No satus report for PCM5122 yet"


def get_lineout_dac(config: DACConfig) -> LineOutDac:
    return LineOutDac.from_cfg(config)


class SQ66LineOutDac(DAC3101):
    @classmethod
    def from_cfg(cls, config: DACConfig) -> Self:
        dac_config = DAC3101Config(
            enabled=config.enabled,
            i2c_bus=1,
            i2c_addr=DAC3101_I2C_ADDR,
            volume=config.startup_volume,
            muted=config.startup_muted,
        )
        return cls(dac_config)

    @property
    def plugged_in(self) -> bool:
        return True

    def report_status(self) -> str:
        return "SQ66 DAC3101 line-out active"


class NoSpeakerDac:
    def __init__(self) -> None:
        self._volume = 0.0
        self._muted = True

    @property
    def enabled(self) -> bool:
        return False

    @property
    def volume(self) -> float:
        return self._volume

    def setup(self) -> None:
        return None

    def set_volume(self, volume: float) -> bool:
        self._volume = float(volume)
        return False

    def set_mute_on(self) -> bool:
        self._muted = True
        return False

    def set_mute_off(self) -> bool:
        self._muted = False
        return False

    def is_muted(self) -> bool:
        return self._muted

    def report_status(self) -> str:
        return "Speaker DAC not available on this board"


class SpeakerDacConfig(DACConfig):
    CONF_GROUPS: ClassVar[tuple[str, ...]] = ("speaker", "tas2780")
    channel: AudioCh = "dwn_mix"
    amp_level: int = Field(8, ge=0, le=0x14)


class SpeakerDac(TAS2780):
    @classmethod
    def from_cfg(
        cls, config: SpeakerDacConfig, power_mode: Literal[0, 1, 2, 3] = 0
    ) -> Self:
        tas_config = TAS2780Config(
            i2c_bus=1,
            i2c_addr=TAS2780_I2C_ADDR,
            enabled=config.enabled,
            volume=config.startup_volume,
            muted=config.startup_muted,
            power_mode=power_mode,
            channel=config.channel,
            amp_level=config.amp_level,
        )
        return cls(tas_config)

    def report_status(self):
        print("Speaker DAC (TAS2780):")
        print(self.get_state())


def get_speaker_dac(config: SpeakerDacConfig) -> SpeakerDac:
    pd_contract: PDContract = get_pd_contract()
    dac_power_mode: Literal[0, 1, 2, 3] = 0
    if pd_contract.voltage and pd_contract.voltage >= 9:
        dac_power_mode = 2

    return SpeakerDac.from_cfg(config, dac_power_mode)


def get_active_dac_id(
    lineout_dac: LineOutDac | SQ66LineOutDac,
    speaker_dac: SpeakerDac | NoSpeakerDac,
    board: BoardId = "satellite1",
) -> DacStr | None:
    if board == "sq66":
        return "line-out" if lineout_dac.enabled else None
    if lineout_dac.enabled and bool(getattr(lineout_dac, "plugged_in", False)):
        return "line-out"
    if speaker_dac.enabled:
        return "speaker"
    return None


def get_sq66_lineout_dac(config: DACConfig) -> SQ66LineOutDac:
    return SQ66LineOutDac.from_cfg(config)


def get_lineout_dac_for_board(
    config: DACConfig, board: BoardId = "satellite1"
) -> LineOutDac | SQ66LineOutDac:
    if board == "sq66":
        return get_sq66_lineout_dac(config)
    return get_lineout_dac(config)


def get_speaker_dac_for_board(
    config: SpeakerDacConfig, board: BoardId = "satellite1"
) -> SpeakerDac | NoSpeakerDac:
    if board == "sq66":
        return NoSpeakerDac()
    return get_speaker_dac(config)


def setup_dacs(
    lineout_dac: LineOutDac | SQ66LineOutDac,
    speaker_dac: SpeakerDac | NoSpeakerDac,
    board: BoardId = "satellite1",
) -> bool:
    if board == "sq66":
        ioexp = PCAL6408A(PCAL6408AConfig(i2c_bus=1, i2c_addr=PCAL6408A_I2C_ADDR))
        ioexp.setup()
    lineout_dac.setup()
    speaker_dac.setup()
    return True
