# AGENTS.md

Guidance for coding agents working in `Satellite1-RPi`.

## Scope and intent
- This repository hosts the Raspberry Pi SDK and related packaging assets for Satellite1.
- Primary Python package: `satellite1` under `src/`.
- Tests live under `tests/`.
- Toolchain is Python-first with Make targets for local workflows.

## Repository layout
- `src/satellite1/`: SDK code, CLI entrypoints, hardware/component abstractions.
- `tests/`: pytest suite (CLI, config, board selection, component behavior).
- `scripts/`: deployment/verification shell scripts for SQ66 workflows.
- `debian/`, `sys-packages/`, `image-builder/`: packaging and image build support.

## OpenCode execution rules

Use native OpenCode tools by default.
Do not substitute bash for native tools.

- Read files with read/search/glob tools.
- Edit files with edit or patch.
- Create files with write.
- Use bash only for tests, builds, package manager commands, git, and project CLIs.
- Never use bash heredocs or redirection to create or edit files when native file tools exist.
- Never claim a command was run unless the tool was actually called.
- In plan mode, do not try to bypass restrictions with bash.
- If bash is needed, use the smallest possible command.
- If bash validation fails, retry with a short `description` field.
- In plan mode, you are not allowed to call bash, tell the user to switch to build mode



## Python/runtime expectations
- Python version: `>=3.11` (see `pyproject.toml`).
- Preferred local interpreter for Make targets: `python3.11`.
- Local venv path used by Make: `.venv/`.

## Setup commands
- Create venv:
  - `make venv`
- Install dev dependencies:
  - `make dev-install`
- Equivalent direct install:
  - `python3.11 -m venv .venv`
  - `.venv/bin/pip install -e .[dev]`

## Build/lint/test/typecheck commands

### Common quality gates
- Run tests:
  - `make test`
- Run lint:
  - `make lint`
- Run typecheck:
  - `make typecheck`
- Run all checks:
  - `make check`
- Run pre-commit hooks:
  - `make precommit`

### Pytest commands (single test focus)
- Run one test module:
  - `make test-file FILE=tests/test_cli/test_cli_dac.py`
- Run by keyword expression:
  - `make test-k K="sq66 or board_selection"`
- Run one test function/node id directly:
  - `.venv/bin/python -m pytest tests/test_cli/test_cli_dac.py::test_set_volume_sets_value_and_prints -q`
- Run one test class:
  - `.venv/bin/python -m pytest tests/test_components/test_xmos_device_cntrl.py::TestName -q`
- Run one test file directly (without Make):
  - `.venv/bin/python -m pytest tests/test_config_load.py -q`

### Domain-specific test selection
- SQ66-focused selection:
  - `make sq66-test`

## Packaging/build commands
- Build wheel artifacts via Dockerized build:
  - `make build`
- Build Debian package:
  - `make deb`
- Build Docker image used for Debian builds:
  - `make docker-image`
- Build setup/kernel package artifacts:
  - `make rpi-setup-deb`
  - `make kernel-pkg`

## Useful Make variables/options
- Allow dirty tree for build-related targets:
  - `make build ALLOW_DIRTY=1`
- Single-file tests:
  - `make test-file FILE=<path>`
- Keyword tests:
  - `make test-k K='<expr>'`
- SQ66 deploy/verify:
  - `make sq66-deploy-temp HOST=user@ip`
  - `make sq66-verify-temp HOST=user@ip`

## Code style and conventions

### Formatting and linting
- Ruff is the linter and formatter (`ruff` + `ruff-format` via pre-commit).
- Ruff config:
  - target version: `py311`
  - line length: `88`
  - lint selects: `E`, `F`, `I`
  - ignore: `E501` (long lines tolerated when needed)
- Keep formatting compatible with Ruff; do not fight auto-formatting.

### Imports
- Sort/group imports in Ruff/isort-compatible order:
  1. standard library
  2. third-party
  3. local package imports
- Prefer explicit imports over wildcard imports.
- Internal package imports often use relative imports inside `satellite1/*`.

### Typing
- Use type hints broadly (functions, returns, key locals where helpful).
- Prefer modern syntax (`list[str]`, `X | None`).
- Mypy is enabled with:
  - `check_untyped_defs = true`
  - `warn_return_any = true`
- Keep new code mypy-clean under `src/`.
- Hardware-only deps (`spidev`, `RPi.*`) may be unavailable in non-target environments; preserve import-guard patterns where appropriate.

### Naming
- Modules/functions/variables: `snake_case`.
- Classes: `PascalCase`.
- Constants: `UPPER_SNAKE_CASE`.
- CLI commands/options use kebab-case strings (e.g., `set-volume`, `line-out`), while Python identifiers remain snake_case.

### Configuration models
- Pydantic models are used for runtime config and validation.
- Prefer `BaseModel` defaults and explicit field constraints/types.
- Keep config precedence behavior intact:
  - CLI overrides > config file section > model defaults.

### Error handling
- Validate user/config inputs early; raise `ValueError` for invalid argument/value contracts.
- CLI-facing command handlers commonly:
  - print user-visible results
  - return integer status codes
  - raise `SystemExit` for invalid CLI states/usages
- Runtime hardware failures may raise `RuntimeError`.
- Be precise with caught exceptions; broad catches are used sparingly and usually around optional platform dependencies or config probing.

### Logging and output
- Module-level logger pattern: `log = logging.getLogger(__name__)` (or explicit component logger).
- Respect verbosity-driven logging setup used in CLI modules.
- Keep human-facing CLI output concise and deterministic (tests assert printed output).

## Testing conventions
- Framework: `pytest`.
- Common patterns:
  - `monkeypatch` for env/module behavior
  - stubbed hardware modules (`spidev`) for deterministic unit tests
  - `capsys` for CLI output assertions
  - descriptive `test_*` names focused on behavior/contract
- Add/adjust tests when changing CLI behavior, board selection logic, config loading, or protocol encoding/decoding.

## Agent behavior expectations
- Prefer minimal, targeted diffs.
- Update tests with behavior changes.
- Run relevant subset first (single module/node), then broader suite when practical.
- Avoid introducing new tools/config styles unless requested.
- Preserve existing public CLI behavior unless task explicitly changes it.

## Cursor/Copilot instructions status
- No repository-specific Cursor rules were found:
  - `.cursor/rules/` absent
  - `.cursorrules` absent
- No GitHub Copilot instructions were found:
  - `.github/copilot-instructions.md` absent
- If these files are added later, update this document and treat them as authoritative supplements.
