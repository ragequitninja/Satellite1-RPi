---
name: rpi-temp-sdk-deploy
description: Build a wheel from current repo state and install it into a reusable temporary venv on a target Raspberry Pi.
---

## Goal
Deploy and run the current local `Satellite1-RPi` state on a target Pi without touching system installs.

## Rules
- This skill assumes the current repository is the SDK source; do not request a separate SDK path.
- Never use or modify `/opt/satellite1/venv` in this workflow.
- Use a dedicated reusable temporary environment on the target Pi.
- Use Make targets from repository root for deployment orchestration.
- Use wheel-based deployment; do not sync source trees with rsync in this workflow.
- Do not delete remote temp files or temp venv after test runs unless explicitly requested.
- For Debian deploy flows, if the local `make deb` step fails, stop immediately; do not attempt remote copy or install.

## Persistent paths

Local wheel output directory:
- `build-assets`

Remote paths on Pi:
- Wheel cache dir: `/home/pi/.cache/satellite1-rpi-e2e/wheels`
- Temp venv: `/home/pi/.cache/venvs/satellite1-rpi-e2e`

## Required local environment
- Either `HOST` is provided on command line, or `.env` contains host defaults:
  - `SAT1_HOST` for generic deploy targets
  - `SQ66_HOST` for SQ66 alias targets

## Commands
1. Deploy wheel and install into remote temp venv:
   `make deploy-temp HOST="${SAT1_HOST}"`
2. Verify CLI and board-level command path:
   `make verify-temp HOST="${SAT1_HOST}" BOARD=sq66`

SQ66 aliases (equivalent):
- `make sq66-deploy-temp HOST="${SQ66_HOST}"`
- `make sq66-verify-temp HOST="${SQ66_HOST}"`

Optional direct script usage:
- `./scripts/deploy_temp_sdk.sh --host "${SAT1_HOST}"`
- `./scripts/deploy_temp_verify.sh --host "${SAT1_HOST}" --board sq66`

Optional Debian package deployment:
- `make deploy-deb HOST="${SAT1_HOST}"`
- Generic deploy helper script: `./scripts/deploy_deb_package.sh`
- If `make deb` fails during this flow, return the build failure and do not continue to remote install.

## Exit code mapping
- `0`: success
- `10`: local precondition issue (missing args, tools, host)
- `20`: local wheel build failed
- `30`: remote transfer/connectivity failure
- `40`: remote venv/pip install failure
- `50`: CLI smoke verification failure
- `60`: board runtime command failure

## Output format
- Command run
- Result summary
- Exit code category (when non-zero)
- Suggested next command

## Reusable command for tests

For CLI-only tests, use:

`/home/pi/.cache/venvs/satellite1-rpi-e2e/bin/sat1 --config /home/pi/.cache/satellite1-rpi-e2e/satellite1.conf`

For XMOS HIL suites that use both CLI commands and remote Python `-c` snippets,
create a wrapper once and reuse it:

`/home/pi/.cache/satellite1-rpi-e2e/sat1_or_python.sh`

Wrapper content:

```bash
#!/usr/bin/env bash
set -e
if [ "${1:-}" = "-c" ]; then
  exec /home/pi/.cache/venvs/satellite1-rpi-e2e/bin/python "$@"
fi
exec /home/pi/.cache/venvs/satellite1-rpi-e2e/bin/sat1 --config /home/pi/.cache/satellite1-rpi-e2e/satellite1.conf "$@"
```

Set executable bit:

`chmod +x /home/pi/.cache/satellite1-rpi-e2e/sat1_or_python.sh`

Example:

`make verify-temp HOST="${SAT1_HOST}" BOARD=sq66`

## Notes
- This workflow is for temporary validation only.
- It intentionally avoids changing apt-managed binaries and system venvs.
- Because paths are persistent, repeated runs should only transfer changed files.
