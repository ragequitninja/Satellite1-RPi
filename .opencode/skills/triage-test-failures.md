name: triage-test-failures
description: Classify failing tests and propose minimal fix sequence.

## Goal
Turn raw pytest output into actionable steps.

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
- `which python` and `python --version`
- `.venv/bin/python --version`
- dependency import errors
- changed files linked to failure stack trace

## Output format
- Root cause category
- Minimal fix
- Validation command
- Follow-up command
