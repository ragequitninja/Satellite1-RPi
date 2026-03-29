---
name: device-control-handoff-apply
description: Apply XMOS device-control handoff files by routing implementation to the device-control-handoff-updater subagent.
---

## Goal
Turn an XMOS protocol handoff into concrete SDK code/test updates in this repository.

## When to use
- A handoff file from XMOS exists (for example `docs/handoffs/rpi-sdk/*.md`)
- A prompt includes protocol/servicer deltas that must be applied in Satellite1-RPi

## Routing
- Always delegate implementation to subagent:
  - `.opencode/agents/device-control-handoff-updater.md`

## Required input
- One of:
  - Handoff file path
  - Handoff content pasted in prompt

## Workflow
1. Read the handoff and extract resource/command/payload/status deltas.
2. Launch `device-control-handoff-updater` with the extracted requirements.
3. Implement code and tests in small, protocol-focused changes.
4. Run targeted tests first, then broader relevant tests.
5. Report implemented items, remaining gaps, and compatibility assumptions.

## Rules
- Preserve backward compatibility unless handoff explicitly says otherwise.
- Keep packaging/deployment out of scope unless handoff requires it.
- Do not mix unrelated refactors into handoff implementation commits.
