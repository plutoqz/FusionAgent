# Consolidation Backlog

## P0

- ToolSpec registry
  - tests: registry shape, executor lookup, input or output contract enforcement
  - runtime artifact: tool or handler evidence in `plan.json` and `audit.jsonl`
  - inspection surface: run inspection must expose contract failure cause
  - operations wording: registered tool contracts
- KG grounding report
  - tests: per-step grounding payload and missing-evidence behavior
  - runtime artifact: grounding entries in `plan.json` and `audit.jsonl`
  - inspection surface: per-step grounding summary
  - operations wording: KG grounding report
- unsupported-intent rejection
  - tests: out-of-scope request guard and machine-readable rejection reason
  - runtime artifact: explicit unsupported-intent audit event
  - inspection surface: failure or clarification summary
  - operations wording: unsupported-intent rejection
- telemetry
  - tests: latency, token, and phase telemetry service behavior
  - runtime artifact: timing and token markers in run artifacts
  - inspection surface: phase progress and stale-run visibility
  - operations wording: token or latency telemetry
- checkpoint recovery inspection
  - tests: stale-run scan and recovery action classification
  - runtime artifact: checkpoint and stale-run metadata
  - inspection surface: recovery recommendation summary
  - operations wording: checkpoint recovery inspection

## P1

- scenario dependency enrichment
- path prioritization for planner retrieval
- operator summary consolidation

## P2

- front-end evidence views
- richer ablation automation
- research utility cleanup

## Priority Rule

- Do not promote a P0 item into README or thesis wording until its tests, runtime artifact, inspection surface, and operations wording all exist.
- P1 may start only after the P0 evidence hooks are closed.
- P2 remains optional and should not displace the core-next runtime hardening chain.

