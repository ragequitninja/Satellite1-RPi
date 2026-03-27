from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path
from typing import Literal

from .config_load import DEFAULT_PATHS

BoardId = Literal["satellite1", "sq66"]

DEFAULT_BOARD: BoardId = "satellite1"
log = logging.getLogger(__name__)


def _normalize_board(value: str | None) -> BoardId | None:
    if value is None:
        return None
    key = value.strip().lower()
    aliases: dict[str, BoardId] = {
        "satellite1": "satellite1",
        "sat1": "satellite1",
        "sq66": "sq66",
        "xk_voice_sq66": "sq66",
        "xk-voice-sq66": "sq66",
    }
    return aliases.get(key)


def _board_from_config(config_path: Path | None) -> BoardId | None:
    if config_path is None:
        config_path = next((p for p in DEFAULT_PATHS if p.exists()), None)
    if config_path is None or not config_path.exists():
        return None
    try:
        with config_path.open("rb") as f:
            raw = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        log.warning("Unable to read board from %s: %s", config_path, exc)
        return None

    for key in ("global", "sat1", "satellite1"):
        section = raw.get(key)
        if isinstance(section, dict):
            board = _normalize_board(section.get("board"))
            if board:
                return board

    return _normalize_board(raw.get("board"))


def resolve_board(cli_board: str | None, config_path: Path | None = None) -> BoardId:
    board = _normalize_board(cli_board)
    if board:
        return board

    board = _normalize_board(os.getenv("SAT1_BOARD"))
    if board:
        return board

    board = _board_from_config(config_path)
    if board:
        return board

    return DEFAULT_BOARD
