# Complexity Boundary Ledger

## Purpose

This ledger separates core runtime proof from optional or deferred complexity. Use it to keep the next improvement chain focused on evidence that directly supports the current no-UI FusionAgent claim.

## Boundary Ledger

| System Slice | Boundary | Decision | Rationale |
| --- | --- | --- | --- |
| planner -> validator -> executor -> healing/replan -> writeback | core | keep | main runtime claim |
| KG context and validator | core | keep | required for constrained planning |
| audit/run/plan/validation artifacts | core | keep | required for no-UI observability |
| ToolSpec registry | core next | add | converts handlers into enforceable contracts |
| plan grounding report | core next | add | proves KG evidence per step |
| unsupported request guard | core next | add | prevents silent misuse |
| step heartbeat and recovery scanner | core next | add | minimum credible long-run operations layer |
| Benin source profiling and cleanup scripts | optional | keep but demote | useful research utilities, not the main runtime contract |
| Benin multi-source building scripts | deferred | freeze runtime claim | do not promote into the stable runtime story without shared evidence |
| trajectory-to-road seam | deferred | metadata only | not executable at runtime |
| durable learning | optional | simplify claims | bounded policy hints, not autonomous self-evolution |
| artifact reuse branches | optional | keep but document | useful, but not the core proof |
| operator web workbench polish | optional | keep bounded | useful operator surface, but not the main thesis or runtime proof |

## Operating Rule

Core and `core next` rows are allowed to drive implementation and verification work. Deferred and optional rows may be documented, but they must not become runtime claims unless later evidence upgrades them through tests, artifacts, and operations wording.
