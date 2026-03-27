from __future__ import annotations

from pathlib import Path

import pytest

import satellite1.cli.cli_xmos as x_cli


@pytest.fixture(autouse=True)
def stub_xmos(monkeypatch):
    class FakeXMOS:
        def setup(self):
            return True

        def read_firmware(self):
            return "v1.2.3"

        def read_status(self):
            return bytes([0x01, 0x02, 0x03])  # triggers hex formatting

        def reset_xmos(self):
            return True

        def flash_firmware(self, img: Path, verify: bool = False):
            return True

        def set_mic_output_channels(self, left: int, right: int):
            return (left, right) == (1, 2)

        def get_mic_input_settings(self):
            return "MicInputSettings(mic_gain=1, ref_gain=2, ref_source_mode=1, mic_source_mode=0, ref_input_channel_map=(0, 1), mic_input_channel_map=(2, 3))"

        def set_mic_input_gains(self, mic_gain=None, ref_gain=None):
            return True

        def set_mic_input_source_modes(
            self, ref_source_mode=None, mic_source_mode=None
        ):
            return True

        def set_mic_input_channel_maps(
            self, ref_input_channel_map=None, mic_input_channel_map=None
        ):
            return True

    monkeypatch.setattr(x_cli, "XMOS", FakeXMOS, raising=True)
    monkeypatch.setattr(
        x_cli,
        "resolve_board",
        lambda cli_board, config_path: "satellite1",
        raising=True,
    )


def run(argv, capsys):
    rc = x_cli.xmos_main(argv)
    io = capsys.readouterr()
    return rc, io.out.strip()


def test_setup(capsys):
    rc, out = run(["setup"], capsys)
    assert rc == 0 and out == "True"


def test_read_firmware(capsys):
    rc, out = run(["read-firmware"], capsys)
    assert rc == 0 and out == "v1.2.3"


def test_read_status_formats_bytes(capsys):
    rc, out = run(["read-status"], capsys)
    assert rc == 0 and out == "01 02 03"


def test_read_status_handles_missing_payload(capsys, monkeypatch):
    class FakeXMOS:
        def setup(self):
            return True

        def read_firmware(self):
            return "v1.2.3"

        def read_status(self):
            return None

        def reset_xmos(self):
            return True

        def flash_firmware(self, img: Path, verify: bool = False):
            return True

        def set_mic_output_channels(self, left: int, right: int):
            return True

        def get_mic_input_settings(self):
            return ""

        def set_mic_input_gains(self, mic_gain=None, ref_gain=None):
            return True

        def set_mic_input_source_modes(
            self, ref_source_mode=None, mic_source_mode=None
        ):
            return True

        def set_mic_input_channel_maps(
            self, ref_input_channel_map=None, mic_input_channel_map=None
        ):
            return True

    monkeypatch.setattr(x_cli, "XMOS", FakeXMOS, raising=True)
    rc, out = run(["read-status"], capsys)
    assert rc == 1 and out == "None"


def test_reset(capsys):
    rc, out = run(["reset"], capsys)
    assert rc == 0 and out == "True"


def test_flash_firmware_with_verify(capsys, tmp_path):
    img = tmp_path / "factory.bin"
    img.write_bytes(b"")
    rc, out = run(["flash-firmware", str(img), "--verify"], capsys)
    assert rc == 0 and out == "True"


@pytest.mark.parametrize(
    "cmd,args",
    [
        ("reset", []),
        ("enable-flashing", []),
        ("disable-flashing", []),
        ("flash-firmware", ["factory.bin"]),
    ],
)
def test_sq66_blocks_reset_and_flashing_controls(
    capsys, monkeypatch, tmp_path, cmd, args
):
    monkeypatch.setattr(
        x_cli,
        "resolve_board",
        lambda cli_board, config_path: "sq66",
        raising=True,
    )

    argv = ["--board", "sq66", cmd]
    if cmd == "flash-firmware":
        img = tmp_path / "factory.bin"
        img.write_bytes(b"")
        argv = ["--board", "sq66", cmd, str(img)]
    else:
        argv.extend(args)

    with pytest.raises(SystemExit) as excinfo:
        run(argv, capsys)

    assert "not available on sq66" in str(excinfo.value)


def test_sq66_allows_read_status(capsys, monkeypatch):
    monkeypatch.setattr(
        x_cli,
        "resolve_board",
        lambda cli_board, config_path: "sq66",
        raising=True,
    )
    rc, out = run(["--board", "sq66", "read-status"], capsys)
    assert rc == 0 and out == "01 02 03"


def test_verbose_flags_do_not_crash(capsys):
    assert run(["-v", "setup"], capsys)[0] == 0
    assert run(["-vv", "setup"], capsys)[0] == 0


def test_set_mic_output_uses_new_wrapper(capsys):
    rc, out = run(["set-mic-output", "1", "2"], capsys)
    assert rc == 0


def test_get_mic_input_settings(capsys):
    rc, out = run(["get-mic-input-settings"], capsys)
    assert rc == 0
    assert "MicInputSettings" in out


def test_set_mic_input_gains(capsys):
    rc, out = run(
        ["set-mic-input-gains", "--mic-gain", "12", "--ref-gain", "34"], capsys
    )
    assert rc == 0
    assert out == "True"


def test_set_mic_input_routing(capsys):
    rc, out = run(
        [
            "set-mic-input-routing",
            "--ref-source-mode",
            "1",
            "--mic-source-mode",
            "0",
            "--ref-input-channel-map",
            "0",
            "1",
            "--mic-input-channel-map",
            "2",
            "3",
        ],
        capsys,
    )
    assert rc == 0
    assert out == "True"


def test_set_mic_input_routing_requires_one_arg(capsys):
    with pytest.raises(SystemExit) as excinfo:
        run(["set-mic-input-routing"], capsys)
    assert "at least one routing option must be provided" in str(excinfo.value)


def test_set_mic_output_returns_failure_code(capsys, monkeypatch):
    class FakeXMOS:
        def setup(self):
            return True

        def read_firmware(self):
            return "v1.2.3"

        def read_status(self):
            return bytes([0x01, 0x02, 0x03])

        def reset_xmos(self):
            return True

        def flash_firmware(self, img: Path, verify: bool = False):
            return True

        def set_mic_output_channels(self, left: int, right: int):
            return False

        def get_mic_input_settings(self):
            return ""

        def set_mic_input_gains(self, mic_gain=None, ref_gain=None):
            return True

        def set_mic_input_source_modes(
            self, ref_source_mode=None, mic_source_mode=None
        ):
            return True

        def set_mic_input_channel_maps(
            self, ref_input_channel_map=None, mic_input_channel_map=None
        ):
            return True

    monkeypatch.setattr(x_cli, "XMOS", FakeXMOS, raising=True)
    rc, _ = run(["set-mic-output", "1", "2"], capsys)
    assert rc == 1


def test_read_firmware_handles_missing_payload(capsys, monkeypatch):
    class FakeXMOS:
        def setup(self):
            return True

        def read_firmware(self):
            return None

        def read_status(self):
            return bytes([0x01, 0x02, 0x03])

        def reset_xmos(self):
            return True

        def flash_firmware(self, img: Path, verify: bool = False):
            return True

        def set_mic_output_channels(self, left: int, right: int):
            return True

        def get_mic_input_settings(self):
            return ""

        def set_mic_input_gains(self, mic_gain=None, ref_gain=None):
            return True

        def set_mic_input_source_modes(
            self, ref_source_mode=None, mic_source_mode=None
        ):
            return True

        def set_mic_input_channel_maps(
            self, ref_input_channel_map=None, mic_input_channel_map=None
        ):
            return True

    monkeypatch.setattr(x_cli, "XMOS", FakeXMOS, raising=True)
    rc, out = run(["read-firmware"], capsys)
    assert rc == 1 and out == "None"
