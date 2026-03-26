# tests/test_xmos_firmware_parse.py
from types import SimpleNamespace

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
