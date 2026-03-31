# src/satellite1/cli/cli_xmos.py
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from ..board import resolve_board
from ..components.flashrom_wrapper import FlashromError
from ..sat1_hat import XMOS

log = logging.getLogger(__name__)

MAX_MIC_INPUT_CHANNEL_MAP_LEN = 4


def _resolve_mic_input_channel_map(
    xmos: XMOS, mic_input_channel_map: list[int] | None
) -> tuple[int, int, int, int] | None:
    if mic_input_channel_map is None:
        return None

    if len(mic_input_channel_map) > MAX_MIC_INPUT_CHANNEL_MAP_LEN:
        raise SystemExit(
            f"mic input channel map supports at most {MAX_MIC_INPUT_CHANNEL_MAP_LEN} values"
        )

    available_mic_count = xmos.get_available_mic_count()
    if not 0 < available_mic_count <= MAX_MIC_INPUT_CHANNEL_MAP_LEN:
        raise SystemExit(
            f"invalid available mic count reported by firmware: {available_mic_count}"
        )

    if len(mic_input_channel_map) != available_mic_count:
        raise SystemExit(
            "mic input channel map must provide exactly "
            f"{available_mic_count} values for this firmware"
        )

    if available_mic_count == MAX_MIC_INPUT_CHANNEL_MAP_LEN:
        return (
            mic_input_channel_map[0],
            mic_input_channel_map[1],
            mic_input_channel_map[2],
            mic_input_channel_map[3],
        )

    settings = xmos.get_mic_input_settings()
    resolved = list(mic_input_channel_map) + list(
        settings.mic_input_channel_map[available_mic_count:]
    )
    return (resolved[0], resolved[1], resolved[2], resolved[3])


def _fmt_status(val) -> str:
    """Best-effort human-readable status."""
    try:
        # If it looks like your DeviceCntrlStatusRegister dataclass
        ds = getattr(val, "device_status", None)
        pa = getattr(val, "gpio_port_a", None)
        pb = getattr(val, "gpio_port_b", None)
        if ds is not None and pa is not None and pb is not None:
            return f"device_status=0x{ds:02X} gpio_a=0x{pa:02X} gpio_b=0x{pb:02X}"
    except Exception:
        pass
    # Fallbacks
    if isinstance(val, (bytes, bytearray)):
        return " ".join(f"{b:02X}" for b in val)
    return repr(val)


def _mic_input_settings_to_dict(settings) -> dict:
    return {
        "mic_gain": int(settings.mic_gain),
        "ref_gain": int(settings.ref_gain),
        "ref_source_mode": int(settings.ref_source_mode),
        "mic_source_mode": int(settings.mic_source_mode),
        "ref_input_channel_map": [int(v) for v in settings.ref_input_channel_map],
        "mic_input_channel_map": [int(v) for v in settings.mic_input_channel_map],
    }


def _mic_output_settings_to_dict(settings) -> dict:
    return {
        "pack_extra_upsample_channels": int(settings.pack_extra_upsample_channels),
        "i2s_channel_map": [int(v) for v in settings.i2s_channel_map],
        "upsample_channel_map": [int(v) for v in settings.upsample_channel_map],
    }


def _require_object(name: str, value):
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise SystemExit(f"{name} must be a JSON object")
    return value


def _validate_int_array(name: str, value, expected_len: int) -> list[int]:
    if not isinstance(value, list):
        raise SystemExit(f"{name} must be a JSON array")
    if len(value) != expected_len:
        raise SystemExit(f"{name} must contain exactly {expected_len} values")
    try:
        return [int(v) for v in value]
    except (TypeError, ValueError) as exc:
        raise SystemExit(f"{name} must contain integer values") from exc


def _parse_mic_pipeline_patch(payload: dict) -> tuple[dict, dict]:
    allowed_top = {"mic_input", "mic_output"}
    unknown_top = sorted(set(payload.keys()) - allowed_top)
    if unknown_top:
        raise SystemExit(f"unknown top-level fields: {', '.join(unknown_top)}")

    mic_input_raw = _require_object("mic_input", payload.get("mic_input"))
    mic_output_raw = _require_object("mic_output", payload.get("mic_output"))

    allowed_mic_input = {
        "mic_gain",
        "ref_gain",
        "ref_source_mode",
        "mic_source_mode",
        "ref_input_channel_map",
        "mic_input_channel_map",
    }
    unknown_mic_input = sorted(set(mic_input_raw.keys()) - allowed_mic_input)
    if unknown_mic_input:
        raise SystemExit(f"unknown mic_input fields: {', '.join(unknown_mic_input)}")

    allowed_mic_output = {
        "pack_extra_upsample_channels",
        "i2s_channel_map",
        "upsample_channel_map",
    }
    unknown_mic_output = sorted(set(mic_output_raw.keys()) - allowed_mic_output)
    if unknown_mic_output:
        raise SystemExit(f"unknown mic_output fields: {', '.join(unknown_mic_output)}")

    mic_input_patch: dict = {}
    for key in ("mic_gain", "ref_gain", "ref_source_mode", "mic_source_mode"):
        if key in mic_input_raw:
            try:
                mic_input_patch[key] = int(mic_input_raw[key])
            except (TypeError, ValueError) as exc:
                raise SystemExit(f"mic_input.{key} must be an integer") from exc

    if "ref_input_channel_map" in mic_input_raw:
        mic_input_patch["ref_input_channel_map"] = _validate_int_array(
            "mic_input.ref_input_channel_map",
            mic_input_raw["ref_input_channel_map"],
            2,
        )

    if "mic_input_channel_map" in mic_input_raw:
        mic_input_patch["mic_input_channel_map"] = _validate_int_array(
            "mic_input.mic_input_channel_map",
            mic_input_raw["mic_input_channel_map"],
            4,
        )

    mic_output_patch: dict = {}
    if "pack_extra_upsample_channels" in mic_output_raw:
        val = mic_output_raw["pack_extra_upsample_channels"]
        if isinstance(val, bool):
            mic_output_patch["pack_extra_upsample_channels"] = int(val)
        elif val in (0, 1):
            mic_output_patch["pack_extra_upsample_channels"] = int(val)
        else:
            raise SystemExit(
                "mic_output.pack_extra_upsample_channels must be 0/1 or bool"
            )

    if "i2s_channel_map" in mic_output_raw:
        mic_output_patch["i2s_channel_map"] = _validate_int_array(
            "mic_output.i2s_channel_map",
            mic_output_raw["i2s_channel_map"],
            2,
        )

    if "upsample_channel_map" in mic_output_raw:
        mic_output_patch["upsample_channel_map"] = _validate_int_array(
            "mic_output.upsample_channel_map",
            mic_output_raw["upsample_channel_map"],
            6,
        )

    if not mic_input_patch and not mic_output_patch:
        raise SystemExit("set-mic-pipeline-settings needs at least one field to update")

    return mic_input_patch, mic_output_patch


def _normalize_sample(val) -> str:
    if val is None:
        return "None"
    return " ".join(str(val).split())


def _collect_samples(getter, iterations: int, delay_s: float) -> list[str]:
    samples: list[str] = []
    for idx in range(iterations):
        samples.append(_normalize_sample(getter()))
        if delay_s > 0 and idx < iterations - 1:
            time.sleep(delay_s)
    return samples


def _doa_reading_to_dict(reading) -> dict:
    return {
        "doa_mrad": int(reading.doa_mrad),
        "seq": int(reading.seq),
        "valid": int(reading.valid),
    }


def _handle(args: argparse.Namespace) -> int:
    """Dispatch XMOS subcommands."""
    board = resolve_board(getattr(args, "board", None), getattr(args, "config", None))
    guarded_cmds = {"reset", "enable-flashing", "disable-flashing", "flash-firmware"}
    if board == "sq66" and args.cmd in guarded_cmds:
        raise SystemExit("XMOS reset/flashing controls are not available on sq66")

    xmos = XMOS()

    # Non-SPI commands
    if args.cmd == "enable-flashing":
        xmos.set_flash_mode()
        return 0

    if args.cmd == "disable-flashing":
        xmos.unset_flash_mode()
        return 0

    if args.cmd == "reset":
        ok = xmos.reset_xmos()
        log.info("Reset: %s", ok)
        print(ok)
        return 0 if ok else 1

    if args.cmd == "flash-firmware":
        try:
            if os.geteuid() != 0:
                print(
                    "Warning: XMOS flashing usually requires elevated privileges; rerun with sudo if this fails.",
                    file=sys.stderr,
                )
        except AttributeError:
            pass

        try:
            xmos.flash_firmware(args.img, verify=args.verify)
        except FlashromError as exc:
            msg = f"{exc.stderr}\n{exc.stdout}\n{exc}".lower()
            if any(
                hint in msg
                for hint in (
                    "permission denied",
                    "operation not permitted",
                    "/dev/spidev",
                    "gpio",
                )
            ):
                print(
                    f"Flash failed due to permissions. Try: sudo sat1 xmos flash-firmware {args.img} --verify",
                    file=sys.stderr,
                )
            raise SystemExit(f"flash-firmware failed: {exc}") from exc
        log.info("Flashed %s (verify=%s): True", args.img, args.verify)
        print(True)
        return 0

    # SPI Commands
    log.info("Init SPI")
    xmos.setup()
    if args.cmd == "setup":
        log.info("XMOS setup: True")
        print(True)
        return 0

    if args.cmd == "read-firmware":
        fw = xmos.read_firmware()
        log.info("Firmware: %s", fw)
        print(fw)
        return 0 if fw is not None else 1

    if args.cmd == "read-status":
        st = xmos.read_status()
        log.info("Status: %s", _fmt_status(st) if st is not None else "None")
        print(_fmt_status(st) if st is not None else None)
        return 0 if st is not None else 1

    if args.cmd == "check-spi-consistency":
        if args.iterations < 2:
            raise SystemExit("--iterations must be >= 2")

        firmware_samples = _collect_samples(
            xmos.read_firmware,
            args.iterations,
            args.delay_s,
        )
        status_samples = _collect_samples(
            lambda: _fmt_status(xmos.read_status()),
            args.iterations,
            args.delay_s,
        )

        firmware_unique = sorted(set(firmware_samples))
        status_unique = sorted(set(status_samples))

        fw_ok = len(firmware_unique) == 1 and firmware_unique[0] != "None"
        st_ok = len(status_unique) == 1 and status_unique[0] != "None"

        print(
            "firmware_consistent="
            f"{fw_ok} unique={len(firmware_unique)} value={firmware_unique[0] if firmware_unique else 'None'}"
        )
        print(
            "status_consistent="
            f"{st_ok} unique={len(status_unique)} value={status_unique[0] if status_unique else 'None'}"
        )

        if not fw_ok:
            print(f"firmware_samples={firmware_samples}")
        if not st_ok:
            print(f"status_samples={status_samples}")

        return 0 if (fw_ok and st_ok) else 1

    if args.cmd == "set-mic-output":
        log.info(f"Set mic channels to {args.left} and {args.right}")
        return 0 if xmos.set_mic_output_channels(args.left, args.right) else 1

    if args.cmd == "get-mic-input-settings":
        settings = xmos.get_mic_input_settings()
        print(settings)
        return 0

    if args.cmd == "get-mic-pipeline-settings":
        settings = {
            "available_mic_count": int(xmos.get_available_mic_count()),
            "mic_input": _mic_input_settings_to_dict(xmos.get_mic_input_settings()),
            "mic_output": _mic_output_settings_to_dict(xmos.get_mic_output_settings()),
        }
        if args.json:
            print(json.dumps(settings))
        else:
            print(settings)
        return 0

    if args.cmd == "set-mic-pipeline-settings":
        try:
            payload = json.loads(args.json)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"invalid JSON payload: {exc}") from exc
        if not isinstance(payload, dict):
            raise SystemExit("--json payload must be a JSON object")

        mic_input_patch, mic_output_patch = _parse_mic_pipeline_patch(payload)

        ok = True
        if mic_input_patch:
            if any(k in mic_input_patch for k in ("mic_gain", "ref_gain")):
                ok = (
                    xmos.set_mic_input_gains(
                        mic_gain=mic_input_patch.get("mic_gain"),
                        ref_gain=mic_input_patch.get("ref_gain"),
                    )
                    and ok
                )

            if any(
                k in mic_input_patch
                for k in ("ref_input_channel_map", "mic_input_channel_map")
            ):
                ok = (
                    xmos.set_mic_input_channel_maps(
                        ref_input_channel_map=mic_input_patch.get(
                            "ref_input_channel_map"
                        ),
                        mic_input_channel_map=mic_input_patch.get(
                            "mic_input_channel_map"
                        ),
                    )
                    and ok
                )

            if any(
                k in mic_input_patch for k in ("ref_source_mode", "mic_source_mode")
            ):
                ok = (
                    xmos.set_mic_input_source_modes(
                        ref_source_mode=mic_input_patch.get("ref_source_mode"),
                        mic_source_mode=mic_input_patch.get("mic_source_mode"),
                    )
                    and ok
                )

        if mic_output_patch:
            if "i2s_channel_map" in mic_output_patch:
                left, right = mic_output_patch["i2s_channel_map"]
                ok = xmos.set_mic_output_channels(left, right) and ok

            if (
                "pack_extra_upsample_channels" in mic_output_patch
                or "upsample_channel_map" in mic_output_patch
            ):
                pack_enabled = mic_output_patch.get("pack_extra_upsample_channels")
                if pack_enabled is None:
                    current = xmos.get_mic_output_settings()
                    pack_enabled = int(current.pack_extra_upsample_channels)
                ok = (
                    xmos.set_mic_output_packing(
                        enabled=bool(pack_enabled),
                        mapping=mic_output_patch.get("upsample_channel_map"),
                    )
                    and ok
                )

        print(ok)
        return 0 if ok else 1

    if args.cmd == "get-available-mic-count":
        print(xmos.get_available_mic_count())
        return 0

    if args.cmd == "get-doa":
        if args.mode == "smooth":
            print(xmos.get_doa_smooth())
        else:
            print(xmos.get_doa_raw())
        return 0

    if args.cmd == "doa" and args.doa_cmd == "stream":
        if args.period_s <= 0:
            raise SystemExit("--period-s must be > 0")
        if args.count is not None and args.count <= 0:
            raise SystemExit("--count must be > 0")

        emitted = 0
        try:
            while args.count is None or emitted < args.count:
                sample: dict = {}
                if args.mode in ("raw", "both"):
                    sample["raw"] = _doa_reading_to_dict(xmos.get_doa_raw())
                if args.mode in ("smooth", "both"):
                    sample["smooth"] = _doa_reading_to_dict(xmos.get_doa_smooth())

                print(json.dumps(sample), flush=True)
                emitted += 1

                if args.count is None or emitted < args.count:
                    time.sleep(args.period_s)
        except KeyboardInterrupt:
            return 130
        return 0

    if args.cmd == "get-mic-input-debug-stats":
        print(xmos.get_mic_input_debug_stats())
        return 0

    if args.cmd == "set-mic-input-gains":
        ok = xmos.set_mic_input_gains(
            mic_gain=args.mic_gain,
            ref_gain=args.ref_gain,
        )
        print(ok)
        return 0 if ok else 1

    if args.cmd == "set-mic-input-routing":
        kwargs = {
            "ref_source_mode": args.ref_source_mode,
            "mic_source_mode": args.mic_source_mode,
            "ref_input_channel_map": tuple(args.ref_input_channel_map)
            if args.ref_input_channel_map is not None
            else None,
            "mic_input_channel_map": _resolve_mic_input_channel_map(
                xmos, args.mic_input_channel_map
            ),
        }
        if all(v is None for v in kwargs.values()):
            raise SystemExit("at least one routing option must be provided")
        ok = xmos.set_mic_input_channel_maps(
            ref_input_channel_map=kwargs["ref_input_channel_map"],
            mic_input_channel_map=kwargs["mic_input_channel_map"],
        )
        if ok and (
            kwargs["ref_source_mode"] is not None
            or kwargs["mic_source_mode"] is not None
        ):
            ok = xmos.set_mic_input_source_modes(
                ref_source_mode=kwargs["ref_source_mode"],
                mic_source_mode=kwargs["mic_source_mode"],
            )
        print(ok)
        return 0 if ok else 1

    if args.cmd == "run-spi-test":
        log.info("Starting SPI Test")
        xmos.run_spi_echo_test()
        return 0

    return 2


def attach_to_parser(parser: argparse.ArgumentParser) -> None:
    """
    Attach ALL XMOS commands to `parser` (standalone style).
    Sets `_handler` so the top-level can just call it.
    """
    sp = parser.add_subparsers(dest="cmd", required=True)
    sp.add_parser("setup", help="Initialise SPI/GPIO")
    sp.add_parser("read-firmware", help="Read firmware version")
    sp.add_parser("read-status", help="Read status register")
    check = sp.add_parser(
        "check-spi-consistency",
        help="Run repeated firmware/status reads and report consistency",
    )
    check.add_argument(
        "--iterations",
        type=int,
        default=20,
        help="Number of reads per command (default: 20)",
    )
    check.add_argument(
        "--delay-s",
        type=float,
        default=0.05,
        help="Delay between reads in seconds (default: 0.05)",
    )
    sp.add_parser("reset", help="Toggle reset pin")
    sp.add_parser("enable-flashing", help="Put XMOS in reset (flashing mode)")
    sp.add_parser("disable-flashing", help="Exit XMOS reset mode")
    sp.add_parser("run-spi-test", help="Running the SPI echo test")

    mo = sp.add_parser(
        "set-mic-output", help="Set the output channels of the i2s microphone"
    )
    mo.add_argument("left", type=int)
    mo.add_argument("right", type=int)

    sp.add_parser("get-mic-input-settings", help="Get mic-input pipeline settings")
    sp.add_parser(
        "get-available-mic-count", help="Get available mic-input channel count"
    )
    gps = sp.add_parser(
        "get-mic-pipeline-settings",
        help="Get mic input/output settings and available mic count",
    )
    gps.add_argument(
        "--json",
        action="store_true",
        help="Print output as JSON",
    )

    sps = sp.add_parser(
        "set-mic-pipeline-settings",
        help="Set mic input/output settings using JSON payload",
    )
    sps.add_argument(
        "--json",
        required=True,
        help="JSON payload with mic_input/mic_output partial fields",
    )

    doa = sp.add_parser("get-doa", help="Get latest DoA estimate")
    doa.add_argument(
        "--mode",
        choices=["raw", "smooth"],
        default="raw",
        help="Select DoA signal mode (default: raw)",
    )

    doa_group = sp.add_parser("doa", help="DoA command group")
    doa_sp = doa_group.add_subparsers(dest="doa_cmd", required=True)
    doa_stream = doa_sp.add_parser("stream", help="Stream DoA readings as NDJSON")
    doa_stream.add_argument(
        "--period-s",
        type=float,
        default=0.1,
        help="Sampling period in seconds (default: 0.1)",
    )
    doa_stream.add_argument(
        "--count",
        type=int,
        default=None,
        help="Stop after this many samples (default: run forever)",
    )
    doa_stream.add_argument(
        "--mode",
        choices=["raw", "smooth", "both"],
        default="both",
        help="Select output mode (default: both)",
    )

    sp.add_parser(
        "get-mic-input-debug-stats",
        help="Get frame counter and mean-abs per mic input channel",
    )

    mig = sp.add_parser("set-mic-input-gains", help="Set mic-input gain fields")
    mig.add_argument("--mic-gain", type=int, default=None)
    mig.add_argument("--ref-gain", type=int, default=None)

    mir = sp.add_parser(
        "set-mic-input-routing", help="Set mic-input source modes and channel maps"
    )
    mir.add_argument("--ref-source-mode", type=int, default=None)
    mir.add_argument("--mic-source-mode", type=int, default=None)
    mir.add_argument("--ref-input-channel-map", type=int, nargs=2, default=None)
    mir.add_argument("--mic-input-channel-map", type=int, nargs="+", default=None)

    f = sp.add_parser("flash-firmware", help="Flash factory image")
    f.add_argument("img", type=Path)
    f.add_argument("--verify", action="store_true", help="Verify after flashing")

    parser.set_defaults(_handler=_handle)


def register(
    parent: argparse._SubParsersAction,
    *,
    name: str = "xmos",
    help: str = "XMOS controls",
):
    """
    Register the XMOS component under `parent` subparsers (hub style).
    """
    child = parent.add_parser(name, help=help)
    attach_to_parser(child)
    return child


# -------- Optional: standalone entrypoint (sat1-xmos) --------


def _configure_logging(verbosity: int) -> None:
    level = (
        logging.WARNING
        if verbosity <= 0
        else logging.INFO
        if verbosity == 1
        else logging.DEBUG
    )
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname).1s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    log.debug("Logging configured at %s", logging.getLevelName(level))


def xmos_main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="sat1-xmos", description="Satellite1 XMOS tools")
    # Keep --config at the root for symmetry with other CLIs even if XMOS ignores it today
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="TOML config (unused for XMOS for now)",
    )
    p.add_argument(
        "--board",
        choices=["satellite1", "sq66"],
        default=None,
        help="Hardware board profile (default: satellite1)",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (-v, -vv)",
    )
    attach_to_parser(p)
    args = p.parse_args(argv)
    _configure_logging(args.verbose)
    log.debug("Args: %s", vars(args))
    return int(args._handler(args) or 0)
