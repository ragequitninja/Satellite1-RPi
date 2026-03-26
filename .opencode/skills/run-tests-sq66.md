name: run-tests-sq66
description: Run SQ66-related tests with explicit repo venv and board-aware focus.

## Goal
Validate SQ66 integration paths quickly without running unrelated suites.

## Rules
- Always use `.venv/bin/python`.
- Prefer board-selection and DAC CLI tests first.

## Commands
- SQ66 focused (keyword):
  `.venv/bin/python -m pytest -k "sq66 or board_selection or cli_dac" -q`
- Board resolver:
  `.venv/bin/python -m pytest tests/test_board_selection.py -q`
- DAC path:
  `.venv/bin/python -m pytest tests/test_cli/test_cli_dac.py -q`

## Output format
- Commands run
- What passed
- What failed
- Whether failure is env/setup vs logic/code
