import random
import time
from pathlib import Path
from typing import Callable, Literal

try:
    import RPi.GPIO as GPIO  # type: ignore
except Exception:  # ImportError on macOS, etc.
    GPIO = None

import logging

from .components.xmos_device_cntrl import (
    DFU_SERVICER,
    MAIN_SERVICER,
    SPI_ECHO_SERVICER,
    DeviceCntrlConfig,
    MicInputSettings,
    MicOutputSettings,
    SpeakerSettings,
    XMOSDeviceCntrl,
)
from .components.xmos_device_cntrl import (
    DeviceCntrlStatusRegister as StatusRegister,
)

log = logging.getLogger(__name__)


def _func_name(code: int) -> str:
    # Helpful when debugging
    if GPIO is None:
        return str(code)
    names = {
        GPIO.IN: "IN",
        GPIO.OUT: "OUT",
        getattr(GPIO, "SPI", -1): "SPI",
        getattr(GPIO, "I2C", -1): "I2C",
        getattr(GPIO, "HARD_PWM", -1): "HARD_PWM",
        getattr(GPIO, "SERIAL", -1): "SERIAL",
        getattr(GPIO, "UNKNOWN", -1): "UNKNOWN",
    }
    return names.get(code, str(code))


class XMOS:
    CNTRL_STATUS_LENGTH = 4
    STATUS_READY = 1

    def __init__(self) -> None:
        cntrl_cfg = DeviceCntrlConfig(
            bus=0,
            dev=0,
            max_speed_hz=8_000_000,
            mode=3,
            bits_per_word=8,
            status_reg_len=XMOS.CNTRL_STATUS_LENGTH,
        )

        self._cntrl = XMOSDeviceCntrl(cntrl_cfg)
        self._reset_bcm_pin = 5  # RPi Header 29
        self._status: StatusRegister | None = None
        self._connection_state: Literal["DETACHED", "CNTRL_MODE"] | None = None
        self._state: Literal["DETACHED", "CNTRL_MODE"] | None = None
        self._firmware: str | None = None

    def setup(self, init_spi: bool = True) -> None:
        del init_spi
        self._cntrl.open()

    def read_firmware(self) -> str | None:
        ok, data = self._cntrl.send_cmd(DFU_SERVICER.CMD_GET_VERSION)
        if not ok or data is None or len(data) != 5:
            self.wait_until_ready(timeout_s=3.0, poll_interval_s=0.1)
            ok, data = self._cntrl.send_cmd(DFU_SERVICER.CMD_GET_VERSION)
        if ok and data is not None and len(data) == 5:
            self._firmware = self._fw_from_bytes(data)
            return self._firmware
        return None

    def read_status(self) -> StatusRegister | None:
        ok, data = self._cntrl.send_cmd(MAIN_SERVICER.CMD_NO_OP)
        if ok and data is not None and len(data) == XMOS.CNTRL_STATUS_LENGTH:
            self._status = StatusRegister.from_bytes(data)
            return self._status
        if ok:
            data = bytes(self._cntrl.dc_status_register_[: XMOS.CNTRL_STATUS_LENGTH])
            self._status = StatusRegister.from_bytes(data)
            return self._status
        return None

    def wait_until_ready(
        self, timeout_s: float = 5.0, poll_interval_s: float = 0.1
    ) -> bool:
        deadline = time.monotonic() + timeout_s

        while time.monotonic() < deadline:
            status = self.read_status()
            if status is not None and status.device_status == XMOS.STATUS_READY:
                return True
            time.sleep(poll_interval_s)

        return False

    def reset_xmos(self) -> bool:
        if GPIO is None:
            raise RuntimeError("RPi.GPIO not available")
        GPIO.output(self._reset_bcm_pin, GPIO.HIGH)
        time.sleep(0.1)
        GPIO.output(self._reset_bcm_pin, GPIO.LOW)
        time.sleep(0.1)
        self._connection_state = "DETACHED"
        return True

    def subscribe_status_changes(self, cb: Callable[[StatusRegister], None]) -> None:
        del self, cb
        pass

    def _poll(self) -> None:
        if self._connection_state == "DETACHED":
            if self.read_firmware():
                self._state = "CNTRL_MODE"
        elif self._connection_state == "CNTRL_MODE":
            self.read_status()

    def set_led_states(self) -> None:
        pass

    def _ensure_gpio_setup(self) -> None:
        """Idempotent, strict, and self-validating setup for a BCM pin."""
        if GPIO is None:
            raise RuntimeError("RPi.GPIO not available")
        # 1) Enforce BCM numbering; fail fast if something else chose BOARD
        mode = GPIO.getmode()
        if mode is None:
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            log.debug("GPIO.setmode(BCM)")
        elif mode != GPIO.BCM:
            raise RuntimeError(
                "GPIO mode is BOARD; expected BCM (pin value is BCM index)"
            )

        # 2) Always (re)configure the pin as OUT (cheap and safe)
        GPIO.setup(self._reset_bcm_pin, GPIO.OUT, initial=GPIO.LOW)

        # 3) Validate immediately
        func = GPIO.gpio_function(self._reset_bcm_pin)
        if func != GPIO.OUT:
            raise RuntimeError(
                f"Failed to set GPIO {self._reset_bcm_pin} as OUT (func={_func_name(func)})"
            )
        log.debug("GPIO %d configured as OUT", self._reset_bcm_pin)

    def set_flash_mode(self) -> None:
        self._ensure_gpio_setup()
        log.info("Enabling flashing mode (XMOS in reset state)")
        if GPIO is None:
            raise RuntimeError("RPi.GPIO not available")
        GPIO.output(self._reset_bcm_pin, GPIO.HIGH)

    def unset_flash_mode(self) -> None:
        self._ensure_gpio_setup()
        log.info("Disabling flashing mode (re-init XMOS)")
        if GPIO is None:
            raise RuntimeError("RPi.GPIO not available")
        GPIO.output(self._reset_bcm_pin, GPIO.LOW)

    def flash_firmware(self, img: Path, verify: bool = False) -> None:
        from .components.flashrom_wrapper import Flashrom

        self.set_flash_mode()
        time.sleep(0.5)
        flasher = Flashrom.for_rpi_w25q64jv(timeout=600)
        if not flasher.confirm_chip():
            raise SystemExit("Flash chip not found or not accessible")

        if not img.exists():
            raise ValueError(f"Image-file not found {img}")

        log.info(f"Starting flashing of {img}")
        flasher.write_image(img, verify=verify)

        self.unset_flash_mode()
        self._connection_state = "DETACHED"

    def run_spi_echo_test(self):
        for step in range(10):
            rnd_bytes = random.randbytes(128)
            ok, data = self._cntrl.send_cmd(SPI_ECHO_SERVICER.CMD_SET, rnd_bytes)
            if not ok:
                print("sending failed")
                continue
            ok, data = self._cntrl.send_cmd(SPI_ECHO_SERVICER.CMD_GET)
            if not ok or data != rnd_bytes:
                print(f"step {step} failed:\n  sent: {rnd_bytes!r}\n  recv: {data!r}")
                continue

            print(f"step: {step} passed")

    def set_mic_left_output(self, out_select: int) -> None:
        settings = self.get_mic_output_settings()
        self.set_mic_output_channels(out_select, settings.i2s_channel_map[1])

    def set_mic_right_output(self, out_select: int) -> None:
        settings = self.get_mic_output_settings()
        self.set_mic_output_channels(settings.i2s_channel_map[0], out_select)

    def get_mic_output_settings(self) -> MicOutputSettings:
        return self._cntrl.get_mic_output_settings()

    def set_mic_output_channels(self, left: int, right: int) -> bool:
        return self._cntrl.set_mic_output_settings_partial(
            i2s_channel_map=(left, right)
        )

    def set_mic_output_packing(
        self, enabled: bool, mapping: list[int] | tuple[int, ...] | None = None
    ) -> bool:
        kwargs: dict = {"pack_extra_upsample_channels": enabled}
        if mapping is not None:
            kwargs["upsample_channel_map"] = mapping
        return self._cntrl.set_mic_output_settings_partial(**kwargs)

    def get_speaker_settings(self) -> SpeakerSettings:
        return self._cntrl.get_speaker_settings()

    def set_speaker_eq(self, enabled: bool, profile_id: int | None = None) -> bool:
        return self._cntrl.set_speaker_settings_partial(
            eq_enabled=enabled,
            eq_profile_id=profile_id,
        )

    def get_mic_input_settings(self) -> MicInputSettings:
        return self._cntrl.get_mic_input_settings()

    def set_mic_input_gains(
        self, mic_gain: int | None = None, ref_gain: int | None = None
    ) -> bool:
        return self._cntrl.set_mic_input_settings_partial(
            mic_gain=mic_gain,
            ref_gain=ref_gain,
        )

    @staticmethod
    def _prerelease_str(idx: int) -> str:
        return {1: "alpha", 2: "beta", 3: "rc", 4: "dev"}.get(idx, "")

    def _fw_from_bytes(self, data: bytes):
        if len(data) != 5:
            raise ValueError(f"expected 5 bytes, got {len(data)}")
        maj, mi, pa, pre, pre_n = data
        pre_s = "-" + XMOS._prerelease_str(pre) if pre else ""
        pre_i = f".{pre_n}" if pre and pre_n else ""
        return f"v{maj}.{mi}.{pa}{pre_s}{pre_i}"


def init() -> None:
    pass
