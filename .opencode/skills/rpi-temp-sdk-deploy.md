name: rpi-temp-sdk-deploy
description: Build a wheel from current repo state and install it into a reusable temporary venv on a target Raspberry Pi.

## Goal
Deploy and run the current local `Satellite1-RPi` state on a target Pi without touching system installs.

## Rules
- This skill assumes the current repository is the SDK source; do not request a separate SDK path.
- Never use or modify `/opt/satellite1/venv` in this workflow.
- Use a dedicated reusable temporary environment on the target Pi.
- Use wheel-based deployment; do not sync source trees with rsync in this workflow.
- Do not delete remote temp files or temp venv after test runs unless explicitly requested.

## Persistent paths

Local wheel output directory:
- `build/e2e_wheels`

Remote paths on Pi:
- Wheel cache dir: `/home/pi/.cache/satellite1-rpi-e2e/wheels`
- Temp venv: `/home/pi/.cache/venvs/satellite1-rpi-e2e`

## Required local environment
- `SQ66_RPI_HOST` must be set.

## Deployment sequence
1. Build wheel from current local repo state:
   `.venv/bin/python -m pip wheel --no-deps . -w build/e2e_wheels`
2. Create persistent remote dirs:
   `ssh "${SQ66_RPI_HOST}" "mkdir -p /home/pi/.cache/satellite1-rpi-e2e/wheels /home/pi/.cache/venvs"`
3. Copy the newest built wheel to Pi:
   `scp build/e2e_wheels/satellite1_rpi-*.whl "${SQ66_RPI_HOST}:/home/pi/.cache/satellite1-rpi-e2e/wheels/"`
4. Ensure temp venv exists on Pi:
   `ssh "${SQ66_RPI_HOST}" "python3 -m venv /home/pi/.cache/venvs/satellite1-rpi-e2e"`
5. Install/upgrade wheel in temp venv:
   `ssh "${SQ66_RPI_HOST}" "/home/pi/.cache/venvs/satellite1-rpi-e2e/bin/python -m pip install -U pip setuptools wheel"`
   `ssh "${SQ66_RPI_HOST}" "WHEEL=$(ls -1t /home/pi/.cache/satellite1-rpi-e2e/wheels/satellite1_rpi-*.whl | head -n 1) && /home/pi/.cache/venvs/satellite1-rpi-e2e/bin/python -m pip install -U --force-reinstall \"$WHEEL\""`
6. Verify CLI from temp venv:
   `ssh "${SQ66_RPI_HOST}" "/home/pi/.cache/venvs/satellite1-rpi-e2e/bin/sat1 --help"`

## Reusable command for tests
Use this command prefix on Pi for all temporary test runs:

`/home/pi/.cache/venvs/satellite1-rpi-e2e/bin/sat1`

Example:

`ssh "${SQ66_RPI_HOST}" "/home/pi/.cache/venvs/satellite1-rpi-e2e/bin/sat1 --board sq66 dac setup"`

## Notes
- This workflow is for temporary validation only.
- It intentionally avoids changing apt-managed binaries and system venvs.
- Because paths are persistent, repeated runs should only transfer changed files.
