import logging
import os
import struct
import time
from dataclasses import dataclass
from time import sleep
from typing import Self, Sequence

import fcntl

try:
    import spidev
except Exception:  # pragma: no cover (tests will stub this)
    spidev = None  # type: ignore

log = logging.getLogger("XMOSDeviceCntrl")

MAX_SPI_TRANSFER_LEN = 256


@dataclass(frozen=True)
class DeviceCntrlConfig:
    bus: int = 0
    dev: int = 0
    max_speed_hz: int = 1_000_000
    mode: int = 3
    bits_per_word: int = 8
    status_reg_len: int = 4


class CntrlProto:
    CMD_READ_BIT = 0x80
    CNTRL_RES_ID = 0x01

    RET_DATA_LENGTH_ERROR = 0x03
    RET_DATA_BAD_RESOURCE = 0x05
    RET_IGNORED_IN_DEVICE = 0x07

    RET_PAYLOAD_AVAILABLE = 0x17


@dataclass
class DeviceCntrlCMD:
    resource_id: int
    command_id: int
    payload_len: int

    def __post_init__(self) -> None:
        if not (0 <= self.resource_id <= 0xFF):
            raise ValueError("`resource_id` needs to fit into one byte")
        if not (0 <= self.command_id <= 0xFF):
            raise ValueError("`command_id` needs to fit into one byte")
        if self.payload_len < 0 or (self.payload_len + 3 > MAX_SPI_TRANSFER_LEN):
            raise ValueError(
                f"payload_len needs to be positive and less than {MAX_SPI_TRANSFER_LEN - 3}"
            )


class DFU_SERVICER:
    CMD_GET_VERSION = DeviceCntrlCMD(240, 88 | CntrlProto.CMD_READ_BIT, 5)


class MAIN_SERVICER:
    CMD_NO_OP = DeviceCntrlCMD(0, 0, 0)


class AUDIO_CFG_SERVICER:
    CMD_MIC_LEFT_SELECT = DeviceCntrlCMD(30, 10, 1)
    CMD_MIC_RIGHT_SELECT = DeviceCntrlCMD(30, 11, 1)


class AUDIO_PIPELINE_CONTROL:
    MIC_OUTPUT_SETTINGS_RES_ID = 230
    SPEAKER_SETTINGS_RES_ID = 231
    MIC_INPUT_SETTINGS_RES_ID = 232

    CMD_GET_SETTINGS = 0 | CntrlProto.CMD_READ_BIT
    CMD_SET_SETTINGS_PARTIAL = 1
    CMD_GET_AVAILABLE_MIC_COUNT = 2 | CntrlProto.CMD_READ_BIT
    CMD_GET_DOA_RAW = 3 | CntrlProto.CMD_READ_BIT
    CMD_GET_DOA_SMOOTH = 4 | CntrlProto.CMD_READ_BIT
    CMD_GET_MIC_INPUT_DEBUG_STATS = 5 | CntrlProto.CMD_READ_BIT
    CMD_GET_MIC_INPUT_PACKAGED_SNAPSHOT = 6 | CntrlProto.CMD_READ_BIT
    CMD_GET_SPK_INPUT_PACKAGED_SNAPSHOT = 7 | CntrlProto.CMD_READ_BIT

    MIC_OUTPUT_I2S_CHANNEL_COUNT = 2
    MIC_OUTPUT_PACKED_CHANNEL_COUNT = 6

    MIC_OUTPUT_FIELD_PACK_ENABLE = 1 << 2
    MIC_OUTPUT_FIELD_I2S_CHANNEL_MAP = 1 << 3
    MIC_OUTPUT_FIELD_PACKED_CHANNEL_MAP = 1 << 4
    MIC_OUTPUT_FIELD_OVERWRITE_REF_WITH_IC_NS_OUTPUT = 1 << 9

    SPEAKER_FIELD_EQ_ENABLED = 1 << 0
    SPEAKER_FIELD_EQ_PROFILE_ID = 1 << 1

    MIC_INPUT_FIELD_MIC_GAIN = 1 << 0
    MIC_INPUT_FIELD_REF_GAIN = 1 << 1
    MIC_INPUT_FIELD_REF_SOURCE_MODE = 1 << 5
    MIC_INPUT_FIELD_MIC_SOURCE_MODE = 1 << 6
    MIC_INPUT_FIELD_REF_INPUT_CHANNEL_MAP = 1 << 7
    MIC_INPUT_FIELD_MIC_INPUT_CHANNEL_MAP = 1 << 8

    REF_SOURCE_LEGACY_DOWNSAMPLED = 0
    REF_SOURCE_PACKAGED_INPUT = 1
    MIC_SOURCE_PDM = 0
    MIC_SOURCE_PACKAGED_INPUT = 1


@dataclass(frozen=True)
class MicOutputSettings:
    pack_extra_upsample_channels: int
    i2s_channel_map: tuple[int, int]
    upsample_channel_map: tuple[int, int, int, int, int, int]
    overwrite_ref_with_ic_ns_output: int


@dataclass(frozen=True)
class SpeakerSettings:
    eq_enabled: int
    eq_profile_id: int


@dataclass(frozen=True)
class MicInputSettings:
    mic_gain: int
    ref_gain: int
    ref_source_mode: int
    mic_source_mode: int
    ref_input_channel_map: tuple[int, int]
    mic_input_channel_map: tuple[int, int, int, int]


@dataclass(frozen=True)
class DoaReading:
    doa_mrad: int
    seq: int
    valid: int


@dataclass(frozen=True)
class MicInputDebugStats:
    frame_counter: int
    mic_mean_abs: tuple[int, int, int, int]


@dataclass(frozen=True)
class MicInputPackagedSnapshot:
    magic: int
    guard_a: int
    guard_b: int
    frame_counter: int
    mic_input_channel_map: tuple[int, int, int, int]
    sample_count: int
    packaged_lane_samples: tuple[tuple[int, int, int, int], ...]
    mapped_mic_samples: tuple[tuple[int, int, int, int], ...]


class SPI_ECHO_SERVICER:
    CMD_SET = DeviceCntrlCMD(37, 10, 128)
    CMD_GET = DeviceCntrlCMD(37, 11 | CntrlProto.CMD_READ_BIT, 128)


@dataclass
class DeviceCntrlStatusRegister:
    device_status: int
    gpio_port_a: int
    gpio_port_b: int

    @classmethod
    def from_bytes(cls, data: bytes) -> Self:
        return cls(*map(int, data[:3]))


class XMOSDeviceCntrl:
    def __init__(self, cfg: DeviceCntrlConfig | None = None) -> None:
        self.cfg = cfg or DeviceCntrlConfig()
        self.spi_bus = self.cfg.bus
        self.spi_dev = self.cfg.dev
        self.max_speed_hz = self.cfg.max_speed_hz
        self.mode = self.cfg.mode
        self.bits_per_word = self.cfg.bits_per_word
        self.status_reg_len = self.cfg.status_reg_len

        self._spi = None
        self.dc_status_register_ = bytearray(self.status_reg_len)
        self._may_have_stale_payload = False
        self._lock_fd: int | None = None
        self._lock_path = os.getenv("SAT1_XMOS_SPI_LOCK", "/tmp/sat1_xmos_spi.lock")
        self._lock_timeout_s = float(os.getenv("SAT1_XMOS_SPI_LOCK_TIMEOUT_S", "2.0"))
        self._transfer_count = 0

    @staticmethod
    def _fmt_bytes(data: Sequence[int], limit: int = 12) -> str:
        shown = list(data[:limit])
        suffix = "" if len(data) <= limit else " ..."
        return " ".join(f"{b:02x}" for b in shown) + suffix

    def open(self) -> None:
        if self._spi is not None:
            return
        if spidev is None:  # pragma: no cover
            raise RuntimeError("spidev not available")
        self._acquire_lock()
        spi = spidev.SpiDev()
        spi.open(self.spi_bus, self.spi_dev)  # e.g., /dev/spidev0.0
        spi.max_speed_hz = self.max_speed_hz
        spi.mode = self.mode
        spi.bits_per_word = self.bits_per_word
        self._spi = spi
        log.debug(
            "SPI opened bus=%d dev=%d speed=%dHz mode=%d",
            self.spi_bus,
            self.spi_dev,
            self.max_speed_hz,
            self.mode,
        )

    def close(self) -> None:
        if self._spi is not None:
            try:
                self._spi.close()
            except Exception:
                pass
            self._spi = None
        self._release_lock()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()

    def _acquire_lock(self) -> None:
        if self._lock_fd is not None:
            return
        lock_fd = os.open(self._lock_path, os.O_CREAT | os.O_RDWR, 0o644)
        deadline = time.monotonic() + max(0.0, self._lock_timeout_s)
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self._lock_fd = lock_fd
                return
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(lock_fd)
                    raise RuntimeError(f"SPI lock busy (path={self._lock_path})")
                sleep(0.05)

    def _release_lock(self) -> None:
        if self._lock_fd is None:
            return
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            os.close(self._lock_fd)
        except Exception:
            pass
        self._lock_fd = None

    def dump_config(self) -> dict:
        """Return a small config/status dict (for printing/logging)."""
        return {
            "spi": f"/dev/spidev{self.spi_bus}.{self.spi_dev}",
            "speed_hz": self.max_speed_hz,
            "mode": self.mode,
            "bits": self.bits_per_word,
            "reg_len": self.status_reg_len,
        }

    def send_cmd(
        self, cmd: DeviceCntrlCMD, payload: bytes | bytearray | None = None
    ) -> tuple[bool, bytes | None]:
        return self.transfer(cmd.resource_id, cmd.command_id, payload, cmd.payload_len)

    @staticmethod
    def _validate_channel_index(channel_index: int) -> int:
        if not 0 <= channel_index <= 7:
            raise ValueError("channel index must be in range 0..7")
        return channel_index

    @staticmethod
    def _validate_channel_map(
        name: str, values: Sequence[int], expected_len: int
    ) -> tuple[int, ...]:
        if len(values) != expected_len:
            raise ValueError(f"{name} must contain {expected_len} values")
        return tuple(XMOSDeviceCntrl._validate_channel_index(value) for value in values)

    @staticmethod
    def _validate_bool_u8(name: str, value: bool | int) -> int:
        if isinstance(value, bool):
            return int(value)
        if value in (0, 1):
            return int(value)
        raise ValueError(f"{name} must be 0/1 or bool")

    @staticmethod
    def decode_mic_output_settings(data: bytes) -> MicOutputSettings:
        if len(data) != 10:
            raise ValueError(
                f"expected 10 bytes for mic output settings, got {len(data)}"
            )
        unpacked = struct.unpack("<10B", data)
        return MicOutputSettings(
            pack_extra_upsample_channels=unpacked[0],
            i2s_channel_map=(unpacked[1], unpacked[2]),
            upsample_channel_map=(
                unpacked[3],
                unpacked[4],
                unpacked[5],
                unpacked[6],
                unpacked[7],
                unpacked[8],
            ),
            overwrite_ref_with_ic_ns_output=unpacked[9],
        )

    @staticmethod
    def decode_speaker_settings(data: bytes) -> SpeakerSettings:
        if len(data) != 2:
            raise ValueError(f"expected 2 bytes for speaker settings, got {len(data)}")
        eq_enabled, eq_profile_id = struct.unpack("<2B", data)
        return SpeakerSettings(eq_enabled=eq_enabled, eq_profile_id=eq_profile_id)

    @staticmethod
    def decode_mic_input_settings(data: bytes) -> MicInputSettings:
        if len(data) != 16:
            raise ValueError(
                f"expected 16 bytes for mic input settings, got {len(data)}"
            )
        unpacked = struct.unpack("<2i2B6B", data)
        mic_gain, ref_gain, ref_mode, mic_mode, r0, r1, m0, m1, m2, m3 = unpacked
        return MicInputSettings(
            mic_gain=mic_gain,
            ref_gain=ref_gain,
            ref_source_mode=ref_mode,
            mic_source_mode=mic_mode,
            ref_input_channel_map=(r0, r1),
            mic_input_channel_map=(m0, m1, m2, m3),
        )

    @staticmethod
    def decode_doa_reading(data: bytes) -> DoaReading:
        if len(data) != 8:
            raise ValueError(f"expected 8 bytes for DoA reading, got {len(data)}")
        doa_mrad, seq, valid, _reserved = struct.unpack("<iHBB", data)
        return DoaReading(doa_mrad=doa_mrad, seq=seq, valid=valid)

    @staticmethod
    def decode_mic_input_debug_stats(data: bytes) -> MicInputDebugStats:
        if len(data) != 20:
            raise ValueError(
                f"expected 20 bytes for mic input debug stats, got {len(data)}"
            )
        frame_counter, m0, m1, m2, m3 = struct.unpack("<IIIII", data)
        return MicInputDebugStats(
            frame_counter=frame_counter,
            mic_mean_abs=(m0, m1, m2, m3),
        )

    @staticmethod
    def decode_mic_input_packaged_snapshot(data: bytes) -> MicInputPackagedSnapshot:
        if len(data) != 184:
            raise ValueError(
                f"expected 184 bytes for mic input packaged snapshot, got {len(data)}"
            )
        magic, guard_a, guard_b, frame_counter = struct.unpack_from("<4I", data, 0)
        mic_map = struct.unpack_from("<4B", data, 16)
        sample_count = struct.unpack_from("<I", data, 20)[0]
        lanes = struct.unpack_from("<24i", data, 24)
        mapped = struct.unpack_from("<16i", data, 120)

        packaged_lane_samples = tuple(
            tuple(lanes[i * 4 : (i + 1) * 4]) for i in range(6)
        )
        mapped_mic_samples = tuple(tuple(mapped[i * 4 : (i + 1) * 4]) for i in range(4))

        return MicInputPackagedSnapshot(
            magic=magic,
            guard_a=guard_a,
            guard_b=guard_b,
            frame_counter=frame_counter,
            mic_input_channel_map=tuple(mic_map),
            sample_count=sample_count,
            packaged_lane_samples=packaged_lane_samples,
            mapped_mic_samples=mapped_mic_samples,
        )

    @staticmethod
    def _validate_mode(name: str, value: int, allowed: set[int]) -> int:
        if value not in allowed:
            choices = ", ".join(str(v) for v in sorted(allowed))
            raise ValueError(f"{name} must be one of {{{choices}}}")
        return int(value)

    @staticmethod
    def encode_mic_output_partial(
        *,
        pack_extra_upsample_channels: bool | int | None = None,
        i2s_channel_map: Sequence[int] | None = None,
        upsample_channel_map: Sequence[int] | None = None,
        overwrite_ref_with_ic_ns_output: bool | int | None = None,
    ) -> bytes:
        field_mask = 0
        pack_enable = 0
        i2s_map = [0, 0]
        packed_map = [0] * AUDIO_PIPELINE_CONTROL.MIC_OUTPUT_PACKED_CHANNEL_COUNT
        overwrite_ref = 0

        if pack_extra_upsample_channels is not None:
            field_mask |= AUDIO_PIPELINE_CONTROL.MIC_OUTPUT_FIELD_PACK_ENABLE
            pack_enable = XMOSDeviceCntrl._validate_bool_u8(
                "pack_extra_upsample_channels", pack_extra_upsample_channels
            )

        if i2s_channel_map is not None:
            field_mask |= AUDIO_PIPELINE_CONTROL.MIC_OUTPUT_FIELD_I2S_CHANNEL_MAP
            validated = XMOSDeviceCntrl._validate_channel_map(
                "i2s_channel_map",
                i2s_channel_map,
                AUDIO_PIPELINE_CONTROL.MIC_OUTPUT_I2S_CHANNEL_COUNT,
            )
            i2s_map[:] = validated

        if upsample_channel_map is not None:
            field_mask |= AUDIO_PIPELINE_CONTROL.MIC_OUTPUT_FIELD_PACKED_CHANNEL_MAP
            validated = XMOSDeviceCntrl._validate_channel_map(
                "upsample_channel_map",
                upsample_channel_map,
                AUDIO_PIPELINE_CONTROL.MIC_OUTPUT_PACKED_CHANNEL_COUNT,
            )
            packed_map[:] = validated

        if overwrite_ref_with_ic_ns_output is not None:
            field_mask |= (
                AUDIO_PIPELINE_CONTROL.MIC_OUTPUT_FIELD_OVERWRITE_REF_WITH_IC_NS_OUTPUT
            )
            overwrite_ref = XMOSDeviceCntrl._validate_bool_u8(
                "overwrite_ref_with_ic_ns_output", overwrite_ref_with_ic_ns_output
            )

        if field_mask == 0:
            raise ValueError("at least one mic output setting must be provided")

        return struct.pack(
            "<I10B2x",
            field_mask,
            pack_enable,
            i2s_map[0],
            i2s_map[1],
            packed_map[0],
            packed_map[1],
            packed_map[2],
            packed_map[3],
            packed_map[4],
            packed_map[5],
            overwrite_ref,
        )

    @staticmethod
    def encode_speaker_settings_partial(
        *,
        eq_enabled: bool | int | None = None,
        eq_profile_id: int | None = None,
    ) -> bytes:
        field_mask = 0
        enabled_value = 0
        profile_value = 0

        if eq_enabled is not None:
            field_mask |= AUDIO_PIPELINE_CONTROL.SPEAKER_FIELD_EQ_ENABLED
            enabled_value = XMOSDeviceCntrl._validate_bool_u8("eq_enabled", eq_enabled)

        if eq_profile_id is not None:
            if not 0 <= eq_profile_id <= 0xFF:
                raise ValueError("eq_profile_id must fit into one byte")
            field_mask |= AUDIO_PIPELINE_CONTROL.SPEAKER_FIELD_EQ_PROFILE_ID
            profile_value = eq_profile_id

        if field_mask == 0:
            raise ValueError("at least one speaker setting must be provided")

        return struct.pack("<I2B2x", field_mask, enabled_value, profile_value)

    @staticmethod
    def encode_mic_input_settings_partial(
        *,
        mic_gain: int | None = None,
        ref_gain: int | None = None,
        ref_source_mode: int | None = None,
        mic_source_mode: int | None = None,
        ref_input_channel_map: Sequence[int] | None = None,
        mic_input_channel_map: Sequence[int] | None = None,
    ) -> bytes:
        field_mask = 0
        mic_gain_value = 0
        ref_gain_value = 0
        ref_source_mode_value = 0
        mic_source_mode_value = 0
        ref_map = [0, 0]
        mic_map = [0, 0, 0, 0]

        if mic_gain is not None:
            field_mask |= AUDIO_PIPELINE_CONTROL.MIC_INPUT_FIELD_MIC_GAIN
            mic_gain_value = int(mic_gain)

        if ref_gain is not None:
            field_mask |= AUDIO_PIPELINE_CONTROL.MIC_INPUT_FIELD_REF_GAIN
            ref_gain_value = int(ref_gain)

        if ref_source_mode is not None:
            field_mask |= AUDIO_PIPELINE_CONTROL.MIC_INPUT_FIELD_REF_SOURCE_MODE
            ref_source_mode_value = XMOSDeviceCntrl._validate_mode(
                "ref_source_mode",
                int(ref_source_mode),
                {
                    AUDIO_PIPELINE_CONTROL.REF_SOURCE_LEGACY_DOWNSAMPLED,
                    AUDIO_PIPELINE_CONTROL.REF_SOURCE_PACKAGED_INPUT,
                },
            )

        if mic_source_mode is not None:
            field_mask |= AUDIO_PIPELINE_CONTROL.MIC_INPUT_FIELD_MIC_SOURCE_MODE
            mic_source_mode_value = XMOSDeviceCntrl._validate_mode(
                "mic_source_mode",
                int(mic_source_mode),
                {
                    AUDIO_PIPELINE_CONTROL.MIC_SOURCE_PDM,
                    AUDIO_PIPELINE_CONTROL.MIC_SOURCE_PACKAGED_INPUT,
                },
            )

        if ref_input_channel_map is not None:
            field_mask |= AUDIO_PIPELINE_CONTROL.MIC_INPUT_FIELD_REF_INPUT_CHANNEL_MAP
            validated = XMOSDeviceCntrl._validate_channel_map(
                "ref_input_channel_map", ref_input_channel_map, 2
            )
            ref_map[:] = validated

        if mic_input_channel_map is not None:
            field_mask |= AUDIO_PIPELINE_CONTROL.MIC_INPUT_FIELD_MIC_INPUT_CHANNEL_MAP
            validated = XMOSDeviceCntrl._validate_channel_map(
                "mic_input_channel_map", mic_input_channel_map, 4
            )
            mic_map[:] = validated

        if field_mask == 0:
            raise ValueError("at least one mic input setting must be provided")

        return struct.pack(
            "<I2i2B6B",
            field_mask,
            mic_gain_value,
            ref_gain_value,
            ref_source_mode_value,
            mic_source_mode_value,
            ref_map[0],
            ref_map[1],
            mic_map[0],
            mic_map[1],
            mic_map[2],
            mic_map[3],
        )

    def get_mic_output_settings(self) -> MicOutputSettings:
        ok, data = self.transfer(
            AUDIO_PIPELINE_CONTROL.MIC_OUTPUT_SETTINGS_RES_ID,
            AUDIO_PIPELINE_CONTROL.CMD_GET_SETTINGS,
            None,
            10,
        )
        if not ok or data is None:
            raise RuntimeError("Failed to read mic output settings")
        return self.decode_mic_output_settings(data)

    def set_mic_output_settings_partial(
        self,
        *,
        pack_extra_upsample_channels: bool | int | None = None,
        i2s_channel_map: Sequence[int] | None = None,
        upsample_channel_map: Sequence[int] | None = None,
        overwrite_ref_with_ic_ns_output: bool | int | None = None,
    ) -> bool:
        payload = self.encode_mic_output_partial(
            pack_extra_upsample_channels=pack_extra_upsample_channels,
            i2s_channel_map=i2s_channel_map,
            upsample_channel_map=upsample_channel_map,
            overwrite_ref_with_ic_ns_output=overwrite_ref_with_ic_ns_output,
        )
        ok, _ = self.transfer(
            AUDIO_PIPELINE_CONTROL.MIC_OUTPUT_SETTINGS_RES_ID,
            AUDIO_PIPELINE_CONTROL.CMD_SET_SETTINGS_PARTIAL,
            payload,
            0,
        )
        return ok

    def get_speaker_settings(self) -> SpeakerSettings:
        ok, data = self.transfer(
            AUDIO_PIPELINE_CONTROL.SPEAKER_SETTINGS_RES_ID,
            AUDIO_PIPELINE_CONTROL.CMD_GET_SETTINGS,
            None,
            2,
        )
        if not ok or data is None:
            raise RuntimeError("Failed to read speaker settings")
        return self.decode_speaker_settings(data)

    def set_speaker_settings_partial(
        self,
        *,
        eq_enabled: bool | int | None = None,
        eq_profile_id: int | None = None,
    ) -> bool:
        payload = self.encode_speaker_settings_partial(
            eq_enabled=eq_enabled,
            eq_profile_id=eq_profile_id,
        )
        ok, _ = self.transfer(
            AUDIO_PIPELINE_CONTROL.SPEAKER_SETTINGS_RES_ID,
            AUDIO_PIPELINE_CONTROL.CMD_SET_SETTINGS_PARTIAL,
            payload,
            0,
        )
        return ok

    def get_mic_input_settings(self) -> MicInputSettings:
        ok, data = self.transfer(
            AUDIO_PIPELINE_CONTROL.MIC_INPUT_SETTINGS_RES_ID,
            AUDIO_PIPELINE_CONTROL.CMD_GET_SETTINGS,
            None,
            16,
        )
        if not ok or data is None:
            raise RuntimeError("Failed to read mic input settings")
        return self.decode_mic_input_settings(data)

    def get_available_mic_count(self) -> int:
        ok, data = self.transfer(
            AUDIO_PIPELINE_CONTROL.MIC_INPUT_SETTINGS_RES_ID,
            AUDIO_PIPELINE_CONTROL.CMD_GET_AVAILABLE_MIC_COUNT,
            None,
            1,
        )
        if not ok or data is None or len(data) != 1:
            raise RuntimeError("Failed to read available mic count")
        return data[0]

    def get_doa_raw(self) -> DoaReading:
        ok, data = self.transfer(
            AUDIO_PIPELINE_CONTROL.MIC_INPUT_SETTINGS_RES_ID,
            AUDIO_PIPELINE_CONTROL.CMD_GET_DOA_RAW,
            None,
            8,
        )
        if not ok or data is None:
            raise RuntimeError("Failed to read raw DoA")
        return self.decode_doa_reading(data)

    def get_doa_smooth(self) -> DoaReading:
        ok, data = self.transfer(
            AUDIO_PIPELINE_CONTROL.MIC_INPUT_SETTINGS_RES_ID,
            AUDIO_PIPELINE_CONTROL.CMD_GET_DOA_SMOOTH,
            None,
            8,
        )
        if not ok or data is None:
            raise RuntimeError("Failed to read smooth DoA")
        return self.decode_doa_reading(data)

    def get_mic_input_debug_stats(self) -> MicInputDebugStats:
        ok, data = self.transfer(
            AUDIO_PIPELINE_CONTROL.MIC_INPUT_SETTINGS_RES_ID,
            AUDIO_PIPELINE_CONTROL.CMD_GET_MIC_INPUT_DEBUG_STATS,
            None,
            20,
        )
        if not ok or data is None:
            raise RuntimeError("Failed to read mic input debug stats")
        return self.decode_mic_input_debug_stats(data)

    def get_mic_input_packaged_snapshot(self) -> MicInputPackagedSnapshot:
        ok, data = self.transfer(
            AUDIO_PIPELINE_CONTROL.MIC_INPUT_SETTINGS_RES_ID,
            AUDIO_PIPELINE_CONTROL.CMD_GET_MIC_INPUT_PACKAGED_SNAPSHOT,
            None,
            184,
        )
        if not ok or data is None:
            raise RuntimeError("Failed to read mic input packaged snapshot")
        return self.decode_mic_input_packaged_snapshot(data)

    def set_mic_input_settings_partial(
        self,
        *,
        mic_gain: int | None = None,
        ref_gain: int | None = None,
        ref_source_mode: int | None = None,
        mic_source_mode: int | None = None,
        ref_input_channel_map: Sequence[int] | None = None,
        mic_input_channel_map: Sequence[int] | None = None,
    ) -> bool:
        payload = self.encode_mic_input_settings_partial(
            mic_gain=mic_gain,
            ref_gain=ref_gain,
            ref_source_mode=ref_source_mode,
            mic_source_mode=mic_source_mode,
            ref_input_channel_map=ref_input_channel_map,
            mic_input_channel_map=mic_input_channel_map,
        )
        ok, _ = self.transfer(
            AUDIO_PIPELINE_CONTROL.MIC_INPUT_SETTINGS_RES_ID,
            AUDIO_PIPELINE_CONTROL.CMD_SET_SETTINGS_PARTIAL,
            payload,
            0,
        )
        return ok

    def _drain_pending_read_payloads(self, read_payload_len: int) -> None:
        """
        Drain stale payload-available frames before issuing a fresh read command.

        If a previous read transaction was interrupted, the next read can otherwise
        consume an old payload frame and decode garbage.
        """
        drain_len = max(3, read_payload_len + 1)
        for _ in range(3):
            rx = self._xfer([0x00] * drain_len)
            if not rx or rx[0] != CntrlProto.RET_PAYLOAD_AVAILABLE:
                break

    def transfer(
        self,
        resource_id: int,
        command: int,
        payload: bytes | bytearray | None,
        read_payload_len: int,
    ) -> tuple[bool, bytes | None]:
        """
        Perform a command transaction.
        SPI operates in duplex mode for each byte sent, one is received.

        Wire format (phase 1):
            [resource_id, command, plen_with_readflag, <payload bytes>, <dummy for status…>]
        If READ bit is set, a second short read is performed:
            [0, 0, 0, …] (length = read_len + 3) and payload is returned from index 1..N.

        Returns: (success, response_bytes | None)
        Side effect: updates self.dc_status_register if a status report is observed.
        """
        write_payload = bytes(payload) if payload else b""
        write_payload_len = len(write_payload)
        if command & CntrlProto.CMD_READ_BIT:
            req_payload_len = (
                read_payload_len + 1
            )  # request one more byte for the return status
            if self._may_have_stale_payload:
                self._drain_pending_read_payloads(read_payload_len)
                self._may_have_stale_payload = False
        else:
            req_payload_len = write_payload_len

        # If necessary, we append "dummy" bytes to always allow the device to push the full status register
        status_dummies = max(0, self.status_reg_len - req_payload_len - 1)
        tx = bytearray(3 + req_payload_len + status_dummies)
        tx[0] = resource_id & 0xFF
        tx[1] = command & 0xFF
        tx[2] = req_payload_len & 0xFF
        if write_payload:
            tx[3 : 3 + write_payload_len] = write_payload

        self._transfer_count += 1
        if self._transfer_count == 1:
            log.info(
                "SPI transfer #1 tx_len=%d header=%02x %02x %02x tx=%s",
                len(tx),
                tx[0],
                tx[1],
                tx[2],
                self._fmt_bytes(tx),
            )

        # Retry up to 3 times if device is busy
        for _ in range(5):
            rx = self._xfer(tx)
            if len(rx) < 3:
                log.debug("transfer: short header frame len=%d", len(rx))
                return (False, None)
            # Not responding at all?
            if (rx[0] + rx[1] + rx[2]) == 0:
                log.warning(
                    "transfer: no response (sum header == 0) tx=%s rx=%s",
                    self._fmt_bytes(tx),
                    self._fmt_bytes(rx),
                )
                return (False, None)

            # Transmission got accepted
            if rx[0] != CntrlProto.RET_IGNORED_IN_DEVICE:
                break

            sleep(0.1)
        else:
            # All sending attempts got ignored by the device, give up
            return (False, None)

        # Status register report?
        if rx[0] == CntrlProto.CNTRL_RES_ID and (
            rx[1] != CntrlProto.RET_PAYLOAD_AVAILABLE
        ):
            # [{CNTRL_RES_ID}, {last_cmd_status}] + {status_register}
            n = min(self.status_reg_len, len(rx) - 2)
            if n > 0:
                self.dc_status_register_[:n] = bytes(rx[2 : 2 + n])

        if command & CntrlProto.CMD_READ_BIT:
            # If READ command, do second phase to fetch the payload
            for _ in range(10):
                # send no-op command (0,0,0) for receiving the pending payload
                write_read_len = max(3, req_payload_len)
                rx2 = self._xfer([0x00] * (write_read_len))
                # same ignored retry pattern?
                if rx2[0] == CntrlProto.RET_IGNORED_IN_DEVICE:
                    sleep(0.1)
                    continue

                payload_available = rx2[0] == CntrlProto.RET_PAYLOAD_AVAILABLE
                legacy_dfu_payload = (
                    resource_id == DFU_SERVICER.CMD_GET_VERSION.resource_id
                    and command == DFU_SERVICER.CMD_GET_VERSION.command_id
                    and rx2[0] == 0x00
                )
                legacy_audio_payload = rx2[0] == 0x00 and resource_id in {
                    AUDIO_PIPELINE_CONTROL.MIC_OUTPUT_SETTINGS_RES_ID,
                    AUDIO_PIPELINE_CONTROL.SPEAKER_SETTINGS_RES_ID,
                    AUDIO_PIPELINE_CONTROL.MIC_INPUT_SETTINGS_RES_ID,
                }
                if not (
                    payload_available or legacy_dfu_payload or legacy_audio_payload
                ):
                    sleep(0.05)
                    continue

                if len(rx2) < (1 + read_payload_len):
                    sleep(0.05)
                    continue

                data = (
                    bytes(rx2[1 : 1 + read_payload_len])
                    if read_payload_len > 0
                    else b""
                )
                self._may_have_stale_payload = False
                return (True, data)

            self._may_have_stale_payload = True
            return (False, None)

        # WRITE completed
        return (True, None)

    def _xfer(self, tx: Sequence[int]) -> list[int]:
        if self._spi is None:
            raise RuntimeError("SPI not open")
        # xfer2 keeps CS asserted across the list; full duplex
        return self._spi.xfer2(list(tx))
