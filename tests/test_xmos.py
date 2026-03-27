# tests/test_xmos_firmware_parse.py
from types import SimpleNamespace

import pytest

import satellite1.sat1_hat as sat1_hat_mod
from satellite1.sat1_hat import XMOS


def test_fw_from_bytes_parses():
    x = XMOS()
    assert x._fw_from_bytes(bytes([1, 2, 3, 0, 0])) == "v1.2.3"
    assert x._fw_from_bytes(bytes([1, 2, 3, 1, 5])) == "v1.2.3-alpha.5"


def test_read_status_uses_cached_status_register_bytes():
    x = XMOS()
    x._cntrl = SimpleNamespace(
        dc_status_register_=bytearray([0x11, 0x22, 0x33, 0x44]),
        send_cmd=lambda cmd: (True, None),
    )

    status = x.read_status()

    assert status is not None
    assert status.device_status == 0x11
    assert status.gpio_port_a == 0x22
    assert status.gpio_port_b == 0x33


def test_read_status_uses_no_op_payload_when_available():
    x = XMOS()
    x._cntrl = SimpleNamespace(
        dc_status_register_=bytearray([0x99, 0x88, 0x77, 0x66]),
        send_cmd=lambda cmd: (True, bytes([0x01, 0x02, 0x03, 0x04])),
    )

    status = x.read_status()

    assert status is not None
    assert status.device_status == 0x01
    assert status.gpio_port_a == 0x02
    assert status.gpio_port_b == 0x03


def test_wait_until_ready_returns_true_when_ready_status_seen():
    x = XMOS()
    statuses = iter(
        [
            bytearray([0x00, 0x22, 0x33, 0x44]),
            bytearray([0x01, 0x22, 0x33, 0x44]),
        ]
    )

    def send_cmd(_cmd):
        x._cntrl.dc_status_register_ = next(statuses)
        return True, None

    x._cntrl = SimpleNamespace(
        dc_status_register_=bytearray([0x00, 0x00, 0x00, 0x00]),
        send_cmd=send_cmd,
    )

    assert x.wait_until_ready(timeout_s=0.5, poll_interval_s=0.0) is True


def test_read_firmware_retries_after_wait_even_when_not_ready():
    x = XMOS()
    responses = iter(
        [
            (False, None),
            (True, bytes([1, 2, 3, 0, 0])),
        ]
    )
    calls = {"wait": 0}

    def send_cmd(_cmd):
        return next(responses)

    def fake_wait_until_ready(*, timeout_s: float, poll_interval_s: float) -> bool:
        calls["wait"] += 1
        return False

    x._cntrl = SimpleNamespace(send_cmd=send_cmd)
    x.wait_until_ready = fake_wait_until_ready

    fw = x.read_firmware()

    assert fw == "v1.2.3"
    assert calls["wait"] == 1


def test_set_mic_input_source_modes_forwards_to_control_layer():
    x = XMOS()
    calls = {}

    def set_mic_input_settings_partial(**kwargs):
        calls.update(kwargs)
        return True

    x._cntrl = SimpleNamespace(
        set_mic_input_settings_partial=set_mic_input_settings_partial
    )

    ok = x.set_mic_input_source_modes(ref_source_mode=1, mic_source_mode=0)

    assert ok is True
    assert calls == {"ref_source_mode": 1, "mic_source_mode": 0}


def test_set_mic_input_channel_maps_forwards_to_control_layer():
    x = XMOS()
    calls = {}

    def set_mic_input_settings_partial(**kwargs):
        calls.update(kwargs)
        return True

    x._cntrl = SimpleNamespace(
        set_mic_input_settings_partial=set_mic_input_settings_partial
    )

    ok = x.set_mic_input_channel_maps(
        ref_input_channel_map=(0, 1), mic_input_channel_map=(2, 3)
    )

    assert ok is True
    assert calls == {
        "ref_input_channel_map": (0, 1),
        "mic_input_channel_map": (2, 3),
    }


def test_poll_transitions_to_control_mode_when_firmware_is_read(monkeypatch):
    x = XMOS()
    x._connection_state = "DETACHED"
    monkeypatch.setattr(x, "read_firmware", lambda: "v1.2.3")

    x._poll()

    assert x._connection_state == "CNTRL_MODE"


def test_reset_xmos_calls_gpio_setup_before_toggling(monkeypatch):
    x = XMOS()
    calls: list[str] = []

    class FakeGPIO:
        HIGH = 1
        LOW = 0

        @staticmethod
        def output(_pin: int, _value: int) -> None:
            calls.append("output")

    monkeypatch.setattr(sat1_hat_mod, "GPIO", FakeGPIO)
    monkeypatch.setattr(
        x,
        "_ensure_gpio_setup",
        lambda: calls.append("ensure"),
    )

    assert x.reset_xmos() is True
    assert calls[0] == "ensure"
    assert calls.count("output") == 2


def test_flash_firmware_unsets_flash_mode_on_write_error(monkeypatch, tmp_path):
    from satellite1.components import flashrom_wrapper

    x = XMOS()
    img = tmp_path / "factory.bin"
    img.write_bytes(b"\x01")

    calls: list[str] = []
    monkeypatch.setattr(x, "set_flash_mode", lambda: calls.append("set"))
    monkeypatch.setattr(x, "unset_flash_mode", lambda: calls.append("unset"))

    class FakeFlasher:
        def confirm_chip(self) -> bool:
            return True

        def write_image(self, _img, verify: bool = False) -> None:
            del verify
            raise RuntimeError("write failed")

    monkeypatch.setattr(
        flashrom_wrapper.Flashrom,
        "for_rpi_w25q64jv",
        staticmethod(lambda **_kwargs: FakeFlasher()),
    )

    with pytest.raises(RuntimeError, match="write failed"):
        x.flash_firmware(img)

    assert calls == ["set", "unset"]
