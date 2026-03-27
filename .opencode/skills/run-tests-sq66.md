name: run-tests-sq66
description: Run SQ66-related tests through Make targets with board-aware focus.

## Goal
Validate SQ66 integration paths quickly without running unrelated suites.

## Rules
- Use Make targets only from repository root.
- Prefer board-selection and DAC CLI tests first.

## Commands
- SQ66 focused:
  `make sq66-test`
- Board resolver:
  `make test-file FILE=tests/test_board_selection.py`
- DAC path:
  `make test-file FILE=tests/test_cli/test_cli_dac.py`

## Output format
- Command run
- What passed
- What failed
- Whether failure is env/setup vs logic/code
