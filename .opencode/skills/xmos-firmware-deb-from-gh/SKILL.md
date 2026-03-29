---
name: xmos-firmware-deb-from-gh
description: Download XMOS firmware from a specific GitHub release tag, verify it, and build/deploy the firmware Debian package.
---

## Goal
Produce and optionally deploy `satellite1-xmos-firmware` from a pinned GitHub release version.

## Rules
- Use Make targets from repository root; do not call ad hoc curl/unzip commands directly when this skill is selected.
- Version must be explicit via `XMOS_FW_VERSION` (for reproducible builds).
- Use `.env` defaults when present, with command-line/Make variable override precedence.
- If firmware fetch fails, stop immediately.
- If Debian build fails, stop immediately and do not attempt deploy.
- Package install is payload-only; do not auto-flash as part of package deployment.

## Default release source
- Repo: `FutureProofHomes/Satellite1-XMOS`
- Asset zip: `satellite_firmware_apps.zip`
- Firmware in zip: `satellite1_firmware_fixed_delay.factory.bin`
- MD5 in zip: `satellite1_firmware_fixed_delay.factory.md5`

## .env variables
- `XMOS_FW_REPO`
- `XMOS_FW_ASSET`
- `XMOS_FW_BIN`
- `XMOS_FW_MD5`
- `XMOS_FW_OUT_DIR`

## Commands
1. Fetch and verify firmware payload:
   `make xmos-firmware-fetch XMOS_FW_VERSION=vX.Y.Z`
2. Build firmware Debian package from fetched payload:
   `make xmos-firmware-deb-from-gh XMOS_FW_VERSION=vX.Y.Z`
3. Build and deploy firmware package to a host:
   `make deploy-xmos-firmware-deb-from-gh HOST=user@ip XMOS_FW_VERSION=vX.Y.Z`

## Notes
- Debian package version is normalized by stripping a leading `v` from `XMOS_FW_VERSION`.
- After deployment, flash explicitly when desired:
  `sudo sat1 xmos flash-firmware /usr/share/satellite1/firmware/xmos/current.bin --verify`

## Output format
- Command run
- Resolved firmware version and package artifact path
- Deploy target host (if used)
- Result summary and next command
