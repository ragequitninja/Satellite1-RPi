---
name: triage-test-failures
description: Classify failing tests and propose minimal fix sequence.
---

## Goal
Turn raw test output into actionable steps.

## Rules
- Run from repository root.
- Use Make targets for setup and reruns.
- Prefer the smallest impacted rerun first.

## Commands
- Ensure local setup:
  `make venv` and `make dev-install`
- Targeted validation:
  `make test-file FILE=<path>` or `make test-k K="<pattern>"`
- Broader follow-up:
  `make test` (or `make sq66-test` for board-focused work)

## Procedure
1. Identify first failing test (file + test name).
2. Classify failure:
   - Environment (wrong Python, missing dependency, wrong venv)
   - API mismatch
   - Logic regression
   - Assertion drift
3. Propose smallest fix first.
4. Re-run only impacted tests.
5. Expand to broader suite once green.

## Triage checklist
- dependency import errors
- changed files linked to failure stack trace

## Output format
- Root cause category
- Minimal fix
- Validation command (prefer `make test-file` or `make test-k`)
- Follow-up command (usually `make test`, optionally `make sq66-test`)
