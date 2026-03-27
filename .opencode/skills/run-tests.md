name: run-tests
description: Run project tests through Make targets with reproducible local setup.

## Goal
Run test targets reliably from the repository root and return concise results.

## Rules
- Always run from repository root.
- Use Make targets only; do not call ambient `python` or direct `pytest`.
- Prefer targeted runs first if scope is known.

## Commands
- Full suite:
  `make test`
- Single file:
  `make test-file FILE=tests/test_cli/test_cli_dac.py`
- Pattern:
  `make test-k K="<pattern>"`

## Output format
- Command run
- Pass/fail summary
- First failure with file and assertion
- Suggested next command
