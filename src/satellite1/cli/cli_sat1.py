from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def _configure_logging(verbosity: int) -> None:
    """
    0 -> WARNING, 1 -> INFO, 2+ -> DEBUG
    """
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
    log.debug("Logging configured at level=%s", logging.getLevelName(level))


def register_pd(sp: argparse._SubParsersAction) -> None:
    def _handle(args: argparse.Namespace) -> int:
        from satellite1.components.power_delivery import get_pd_contract

        del args
        print(get_pd_contract())
        return 0

    pd_parser = sp.add_parser("pd", help="Show current power delivery contract.")
    pd_parser.set_defaults(_handler=_handle)


def register_dacs(sp: argparse._SubParsersAction) -> None:
    from .cli_dac import register as _register_dacs

    _register_dacs(sp)


def register_xmos(sp: argparse._SubParsersAction) -> None:
    from .cli_xmos import register as _register_xmos

    _register_xmos(sp)


def _build_base_parser(add_help: bool = True) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="sat1",
        description="Satellite1 HAT control",
        add_help=add_help,
    )
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="TOML config (default: /etc/satellite1.conf)",
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

    return p


def _register_component(sp: argparse._SubParsersAction, component: str | None) -> None:
    if component == "dac":
        register_dacs(sp)
    elif component == "xmos":
        register_xmos(sp)
    elif component == "pd":
        register_pd(sp)
    else:
        register_dacs(sp)
        register_xmos(sp)
        register_pd(sp)


def _build_parser(component: str | None) -> argparse.ArgumentParser:
    p = _build_base_parser()
    sp = p.add_subparsers(dest="component", required=True)
    _register_component(sp, component)
    return p


def build_parser() -> argparse.ArgumentParser:
    return _build_parser(None)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    if any(flag in argv for flag in ("-h", "--help")):
        parser = _build_parser(None)
        args = parser.parse_args(argv)
    else:
        base = _build_base_parser(add_help=False)
        sp = base.add_subparsers(dest="component")
        for name in ("dac", "xmos", "pd"):
            sp.add_parser(name)
        pre, _ = base.parse_known_args(argv)
        parser = _build_parser(getattr(pre, "component", None))
        args = parser.parse_args(argv)

    _configure_logging(args.verbose)
    log.debug("Args: %s", vars(args))

    handler = getattr(args, "_handler", None)
    if handler is None:
        return 2
    return int(handler(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
