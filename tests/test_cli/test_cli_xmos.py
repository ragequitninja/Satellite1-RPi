from __future__ import annotations

import json
from pathlib import Path

import pytest

import satellite1.cli.cli_xmos as x_cli
from satellite1.components.flashrom_wrapper import FlashromError


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
            class _Settings:
                mic_gain = 1
                ref_gain = 2
                ref_source_mode = 1
                mic_source_mode = 0
                ref_input_channel_map = (0, 1)
                mic_input_channel_map = (2, 3, 4, 5)

                def __str__(self):
                    return "MicInputSettings(mic_gain=1, ref_gain=2, ref_source_mode=1, mic_source_mode=0, ref_input_channel_map=(0, 1), mic_input_channel_map=(2, 3, 4, 5))"

            return _Settings()

        def get_available_mic_count(self):
            return 4

        def get_mic_output_settings(self):
            return type(
                "MicOutputSettings",
                (),
                {
                    "pack_extra_upsample_channels": 1,
                    "i2s_channel_map": (0, 3),
                    "upsample_channel_map": (0, 3, 4, 5, 6, 7),
                },
            )()

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

        def set_mic_output_packing(self, enabled: bool, mapping=None):
            return True

        def get_doa_raw(self):
            return type(
                "DoaReading",
                (),
                {
                    "doa_mrad": 123,
                    "seq": 7,
                    "valid": 1,
                    "__str__": lambda _self: "DoaReading(doa_mrad=123, seq=7, valid=1)",
                },
            )()

        def get_doa_smooth(self):
            return type(
                "DoaReading",
                (),
                {
                    "doa_mrad": 100,
                    "seq": 8,
                    "valid": 1,
                    "__str__": lambda _self: "DoaReading(doa_mrad=100, seq=8, valid=1)",
                },
            )()

        def get_mic_input_debug_stats(self):
            return "MicInputDebugStats(frame_counter=42, mic_mean_abs=(10, 20, 30, 40))"

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


def test_check_spi_consistency_passes_when_values_stable(capsys):
    rc, out = run(
        ["check-spi-consistency", "--iterations", "4", "--delay-s", "0"], capsys
    )
    assert rc == 0
    assert "firmware_consistent=True" in out
    assert "status_consistent=True" in out


def test_check_spi_consistency_fails_when_firmware_changes(capsys, monkeypatch):
    class FakeXMOS:
        def __init__(self):
            self._fw_calls = 0

        def setup(self):
            return True

        def read_firmware(self):
            self._fw_calls += 1
            if self._fw_calls % 2 == 0:
                return "v1.2.3"
            return "v9.9.9"

        def read_status(self):
            return bytes([0x01, 0x02, 0x03])

    monkeypatch.setattr(x_cli, "XMOS", FakeXMOS, raising=True)
    rc, out = run(
        ["check-spi-consistency", "--iterations", "4", "--delay-s", "0"], capsys
    )
    assert rc == 1
    assert "firmware_consistent=False" in out
    assert "firmware_samples=" in out


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

        def get_available_mic_count(self):
            return 4

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


def test_flash_firmware_warns_when_not_root(capsys, monkeypatch, tmp_path):
    img = tmp_path / "factory.bin"
    img.write_bytes(b"")
    monkeypatch.setattr(x_cli.os, "geteuid", lambda: 1000)

    rc = x_cli.xmos_main(["flash-firmware", str(img), "--verify"])
    io = capsys.readouterr()

    assert rc == 0 and io.out.strip() == "True"
    assert "usually requires elevated privileges" in io.err


def test_flash_firmware_permission_error_shows_sudo_hint(capsys, monkeypatch, tmp_path):
    class FakeXMOS:
        def flash_firmware(self, img: Path, verify: bool = False):
            del img, verify
            raise FlashromError(
                "flashrom write failed",
                stderr="Permission denied: /dev/spidev0.0",
            )

    img = tmp_path / "factory.bin"
    img.write_bytes(b"")

    monkeypatch.setattr(x_cli, "XMOS", FakeXMOS, raising=True)
    monkeypatch.setattr(x_cli.os, "geteuid", lambda: 1000)

    with pytest.raises(SystemExit) as excinfo:
        x_cli.xmos_main(["flash-firmware", str(img), "--verify"])

    err = capsys.readouterr().err
    assert "flash-firmware failed" in str(excinfo.value)
    assert "Try: sudo sat1 xmos flash-firmware" in err


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


def test_get_available_mic_count(capsys):
    rc, out = run(["get-available-mic-count"], capsys)
    assert rc == 0
    assert out == "4"


def test_get_mic_pipeline_settings_json(capsys):
    rc, out = run(["get-mic-pipeline-settings", "--json"], capsys)
    assert rc == 0
    assert '"available_mic_count": 4' in out
    assert '"mic_input"' in out
    assert '"mic_output"' in out


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
            "4",
            "5",
        ],
        capsys,
    )
    assert rc == 0
    assert out == "True"


def test_set_mic_input_routing_requires_one_arg(capsys):
    with pytest.raises(SystemExit) as excinfo:
        run(["set-mic-input-routing"], capsys)
    assert "at least one routing option must be provided" in str(excinfo.value)


def test_set_mic_pipeline_settings_mic_input_only(capsys, monkeypatch):
    calls = {}

    class FakeXMOS:
        def setup(self):
            return True

        def set_mic_input_gains(self, mic_gain=None, ref_gain=None):
            calls["gains"] = (mic_gain, ref_gain)
            return True

        def set_mic_input_source_modes(
            self, ref_source_mode=None, mic_source_mode=None
        ):
            calls["modes"] = (ref_source_mode, mic_source_mode)
            return True

        def set_mic_input_channel_maps(
            self, ref_input_channel_map=None, mic_input_channel_map=None
        ):
            calls["maps"] = (ref_input_channel_map, mic_input_channel_map)
            return True

    monkeypatch.setattr(x_cli, "XMOS", FakeXMOS, raising=True)

    rc, out = run(
        [
            "set-mic-pipeline-settings",
            "--json",
            '{"mic_input":{"mic_gain":12,"ref_gain":34,"mic_source_mode":1,"ref_source_mode":0,"ref_input_channel_map":[1,2],"mic_input_channel_map":[1,2,3,4]}}',
        ],
        capsys,
    )

    assert rc == 0
    assert out == "True"
    assert calls["gains"] == (12, 34)
    assert calls["modes"] == (0, 1)
    assert calls["maps"] == ([1, 2], [1, 2, 3, 4])


def test_set_mic_pipeline_settings_mic_output_only(capsys, monkeypatch):
    calls = {}

    class FakeXMOS:
        def setup(self):
            return True

        def set_mic_output_channels(self, left: int, right: int):
            calls["channels"] = (left, right)
            return True

        def set_mic_output_packing(self, enabled: bool, mapping=None):
            calls["packing"] = (enabled, mapping)
            return True

    monkeypatch.setattr(x_cli, "XMOS", FakeXMOS, raising=True)

    rc, out = run(
        [
            "set-mic-pipeline-settings",
            "--json",
            '{"mic_output":{"pack_extra_upsample_channels":1,"i2s_channel_map":[2,5],"upsample_channel_map":[0,1,2,3,4,5]}}',
        ],
        capsys,
    )

    assert rc == 0
    assert out == "True"
    assert calls["channels"] == (2, 5)
    assert calls["packing"] == (True, [0, 1, 2, 3, 4, 5])


def test_set_mic_pipeline_settings_rejects_unknown_fields(capsys):
    with pytest.raises(SystemExit) as excinfo:
        run(
            [
                "set-mic-pipeline-settings",
                "--json",
                '{"mic_input":{"unknown":1}}',
            ],
            capsys,
        )
    assert "unknown mic_input fields" in str(excinfo.value)


def test_get_doa_default_raw(capsys):
    rc, out = run(["get-doa"], capsys)
    assert rc == 0
    assert "doa_mrad=123" in out


def test_get_doa_smooth_mode(capsys):
    rc, out = run(["get-doa", "--mode", "smooth"], capsys)
    assert rc == 0
    assert "doa_mrad=100" in out


def test_get_mic_input_debug_stats(capsys):
    rc, out = run(["get-mic-input-debug-stats"], capsys)
    assert rc == 0
    assert "frame_counter=42" in out


def test_doa_stream_emits_ndjson_lines(capsys):
    rc, out = run(["doa", "stream", "--period-s", "0.001", "--count", "3"], capsys)
    assert rc == 0
    lines = out.splitlines()
    assert len(lines) == 3
    for line in lines:
        obj = json.loads(line)
        assert obj["raw"]["doa_mrad"] == 123
        assert obj["smooth"]["doa_mrad"] == 100


def test_doa_stream_raw_mode(capsys):
    rc, out = run(
        ["doa", "stream", "--period-s", "0.001", "--count", "1", "--mode", "raw"],
        capsys,
    )
    assert rc == 0
    obj = json.loads(out)
    assert "raw" in obj
    assert "smooth" not in obj


def test_doa_stream_rejects_non_positive_count(capsys):
    with pytest.raises(SystemExit) as excinfo:
        run(["doa", "stream", "--count", "0"], capsys)
    assert "--count must be > 0" in str(excinfo.value)


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

        def get_available_mic_count(self):
            return 4

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

        def get_available_mic_count(self):
            return 4

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


def test_set_mic_input_routing_pads_to_full_payload_when_firmware_uses_two_mics(
    capsys, monkeypatch
):
    calls = {}

    class FakeXMOS:
        def setup(self):
            return True

        def get_available_mic_count(self):
            return 2

        def get_mic_input_settings(self):
            return type(
                "Settings",
                (),
                {"mic_input_channel_map": (2, 3, 4, 5)},
            )()

        def set_mic_input_channel_maps(
            self, ref_input_channel_map=None, mic_input_channel_map=None
        ):
            calls["ref_input_channel_map"] = ref_input_channel_map
            calls["mic_input_channel_map"] = mic_input_channel_map
            return True

        def set_mic_input_source_modes(
            self, ref_source_mode=None, mic_source_mode=None
        ):
            calls["ref_source_mode"] = ref_source_mode
            calls["mic_source_mode"] = mic_source_mode
            return True

    monkeypatch.setattr(x_cli, "XMOS", FakeXMOS, raising=True)

    rc, out = run(
        [
            "set-mic-input-routing",
            "--mic-input-channel-map",
            "0",
            "1",
        ],
        capsys,
    )

    assert rc == 0
    assert out == "True"
    assert calls["mic_input_channel_map"] == (0, 1, 4, 5)


def test_set_mic_input_routing_rejects_wrong_mic_count(capsys, monkeypatch):
    class FakeXMOS:
        def setup(self):
            return True

        def get_available_mic_count(self):
            return 2

    monkeypatch.setattr(x_cli, "XMOS", FakeXMOS, raising=True)

    with pytest.raises(SystemExit) as excinfo:
        run(["set-mic-input-routing", "--mic-input-channel-map", "0", "1", "2"], capsys)

    assert "exactly 2 values" in str(excinfo.value)
