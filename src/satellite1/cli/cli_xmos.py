# src/satellite1/cli/cli_xmos.py
from __future__ import annotations

import argparse
import logging
from pathlib import Path

from ..board import resolve_board
from ..sat1_hat import XMOS

log = logging.getLogger(__name__)


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
        xmos.flash_firmware(args.img, verify=args.verify)
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

    if args.cmd == "set-mic-output":
        log.info(f"Set mic channels to {args.left} and {args.right}")
        return 0 if xmos.set_mic_output_channels(args.left, args.right) else 1

    if args.cmd == "get-mic-input-settings":
        settings = xmos.get_mic_input_settings()
        print(settings)
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
            "mic_input_channel_map": tuple(args.mic_input_channel_map)
            if args.mic_input_channel_map is not None
            else None,
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

    mig = sp.add_parser("set-mic-input-gains", help="Set mic-input gain fields")
    mig.add_argument("--mic-gain", type=int, default=None)
    mig.add_argument("--ref-gain", type=int, default=None)

    mir = sp.add_parser(
        "set-mic-input-routing", help="Set mic-input source modes and channel maps"
    )
    mir.add_argument("--ref-source-mode", type=int, default=None)
    mir.add_argument("--mic-source-mode", type=int, default=None)
    mir.add_argument("--ref-input-channel-map", type=int, nargs=2, default=None)
    mir.add_argument("--mic-input-channel-map", type=int, nargs=2, default=None)

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
