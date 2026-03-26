name: run-tests
description: Run project tests with the repository venv, never ambient Python.

## Goal
Run test commands reliably with the repo interpreter and return concise results.

## Rules
- Always use `.venv/bin/python`, never bare `python` or `python3`.
- Run from repository root.
- Prefer targeted test runs first if scope is known.

## Commands
- Full suite:
  `.venv/bin/python -m pytest`
- Single file:
  `.venv/bin/python -m pytest tests/test_cli/test_cli_dac.py -q`
- Pattern:
  `.venv/bin/python -m pytest -k "<pattern>" -q`

## Output format
- Interpreter used (`.venv/bin/python --version`)
- Command executed
- Pass/fail summary
- First failure with file and assertion
- Suggested next command
