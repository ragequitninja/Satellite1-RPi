---
name: build-wheel-makefile
description: Build SDK wheel artifacts using the repository Makefile and Docker builder image.
---

## Goal
Build wheel artifacts from the current repo state using the same containerized path defined by `Makefile`.

## Rules
- Prefer `make build` over ad hoc Python build commands when this skill is selected.
- Use `ALLOW_DIRTY=1` for temporary test builds from uncommitted working trees.
- Do not publish artifacts; this workflow is local build only.

## Command
- Standard temporary build:
  `make build ALLOW_DIRTY=1`

## Output location
- Wheels and sdists are written to `build-assets/`.

## Verification
- Confirm wheel exists:
  `ls -la build-assets/satellite1_rpi-*.whl`

## Notes
- The Makefile handles non-interactive sessions by auto-disabling Docker TTY allocation.
- This skill only builds artifacts; deploy/install is handled by dedicated deploy workflows.
