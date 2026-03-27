from __future__ import annotations

from pathlib import Path

from satellite1.board import resolve_board


def test_resolve_board_defaults_to_satellite1(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("SAT1_BOARD", raising=False)
    assert resolve_board(None, tmp_path / "missing.toml") == "satellite1"


def test_resolve_board_uses_env_when_cli_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SAT1_BOARD", "sq66")
    assert resolve_board(None, tmp_path / "missing.toml") == "sq66"


def test_resolve_board_cli_precedence_over_env_and_config(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "satellite1.toml"
    cfg.write_text("[global]\nboard='sq66'\n", encoding="utf-8")
    monkeypatch.setenv("SAT1_BOARD", "sq66")
    assert resolve_board("satellite1", cfg) == "satellite1"


def test_resolve_board_reads_config_global_group(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("SAT1_BOARD", raising=False)
    cfg = tmp_path / "satellite1.toml"
    cfg.write_text("[global]\nboard='sq66'\n", encoding="utf-8")
    assert resolve_board(None, cfg) == "sq66"


def test_resolve_board_invalid_toml_logs_warning_and_falls_back(
    tmp_path: Path, monkeypatch, caplog
):
    monkeypatch.delenv("SAT1_BOARD", raising=False)
    cfg = tmp_path / "satellite1.toml"
    cfg.write_text("[global\nboard='sq66'\n", encoding="utf-8")

    with caplog.at_level("WARNING"):
        board = resolve_board(None, cfg)

    assert board == "satellite1"
    assert "Unable to read board" in caplog.text
