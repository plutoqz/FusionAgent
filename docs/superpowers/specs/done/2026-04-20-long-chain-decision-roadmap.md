# Long-Chain Decision Roadmap

## Purpose

This document defines the longest execution chain that can be planned responsibly from the current repository state.

The chain is:

```text
A. Final Gap Matrix + Evidence Ledger
B. Evaluation Contract + Thesis Claim Lock
C. Full Replan Loop V1
D. Durable Learning -> Policy Hints V1
E. Minimum Research Ontology Closure
F. One New Data/Task Vertical Slice
G. Experiment Matrix + Paper Evidence Freeze
H. Thin Productization / Operator Surface
```

High-confidence phases now:

```text
A -> B -> C -> D
```

Conditional phases:

```text
E -> F -> G -> H
```

The route can be planned now, but detailed implementation plans should remain rolling plans. Each phase ends with a gate review that decides whether to continue, pivot, or stop.

## Global Execution Rules

- Use `codex/*` branches for new work.
- Use global worktrees under `C:\Users\QDX\.config\superpowers\worktrees\fusionAgent` unless the user explicitly overrides.
- Keep Phase A documentation-only; do not change runtime behavior in control-plane work.
- Use subagents for independent read-only inventory and bounded implementation tasks when they reduce context pressure.
- Do not run multiple implementation agents against the same files in parallel.
- Before declaring completion, run verification at least as strong as the phase's verification contract.
- Before merge/push/cleanup, inspect the diff, commit, push, then merge or clean stale worktrees only after the branch is safely integrated.

## Phase A: Final Gap Matrix + Evidence Ledger

Entry condition:

- Current v2 roadmap is closed.
- Main branch test baseline passes.
- User approves autonomous execution along the long-chain decision route.

Minimum deliverable:

- `docs/superpowers/specs/2026-04-20-final-gap-matrix.md`
- `docs/superpowers/specs/2026-04-20-evidence-ledger.md`
- `docs/superpowers/specs/2026-04-20-long-chain-decision-roadmap.md`
- README pointer to the Phase A control plane.

Verification:

```powershell
python -m pytest -q
```

Continue condition:

- Control-plane documents clearly identify Phase B and C as next high-confidence work.
- No placeholder or ambiguous gate remains.

Stop or pivot condition:

- If Phase A reveals that final target is product-only or deployment-only, skip thesis-centric Phase B and write a productization plan instead.

## Phase B: Evaluation Contract + Thesis Claim Lock

Entry condition:

- Phase A documents exist and are committed.

Minimum deliverable:

- A claim map that links each thesis/product claim to required metrics, baselines, datasets, and evidence artifacts.
- A baseline matrix covering full system, KG-only or top-pattern, weakly constrained LLM planning, no-repair execution, and no-learning-hints variants where feasible.
- A decision on which claims are in scope for the next paper-grade evaluation and which are narrative boundaries.

Verification:

- Documentation self-review.
- `python -m pytest -q`
- At least one dry-run command path for `scripts/eval_harness.py` or documented reason why full benchmark execution is deferred.

Continue condition:

- Replan is confirmed as thesis-critical or product-critical.
- Metrics and baselines are clear enough to drive implementation.

Stop or pivot condition:

- If replan is not needed for the scoped claim, skip Phase C and move directly to Phase D or G.

## Phase C: Full Replan Loop V1

Entry condition:

- Phase B confirms replan is a core claim.
- Current healing/repair tests are understood as partial evidence, not full replan proof.

Current touchpoints:

- `services/agent_run_service.py`
- `agent/planner.py`
- `agent/executor.py`
- `agent/validator.py`
- `tests/test_agent_run_service_enhancements.py`
- `tests/test_repair_strategy.py`

Minimum deliverable:

- Failure taxonomy that distinguishes retry, repair, fallback, and true replan.
- Runtime path that creates a replan request from a validated failure.
- Planner path that produces a revised plan while preserving AOI, task bundle, original decisions, and audit history.
- Acceptance gate that records why a new plan is accepted or rejected.

Smallest safe implementation slice:

```text
After `replan_applied`, re-run input acquisition when `input_strategy=task_driven_auto` and the selected source or required input type changed. Add one focused test beside the existing agent-run-service replan coverage.
```

Verification:

- Focused failure-injection tests in `tests/test_agent_run_service_enhancements.py`, `tests/test_workflow_validator.py`, or new focused tests.
- `python -m pytest -q`

Continue condition:

- Replan evidence is deterministic and inspectable.
- Audit output shows old plan, failure reason, new plan, and acceptance decision.

Stop or pivot condition:

- If replan destabilizes current runtime guarantees, freeze C as a documented non-goal and proceed to D/G with current healing claim only.

## Phase D: Durable Learning -> Policy Hints V1

Entry condition:

- Phase C is stable or explicitly scoped down.
- Durable learning records and repository aggregations remain passing.

Current touchpoints:

- `services/agent_run_service.py`
- `kg/models.py`
- `kg/repository.py`
- `kg/inmemory_repository.py`
- `kg/neo4j_repository.py`
- `agent/retriever.py`
- `agent/policy.py`
- `tests/test_kg_repository_enhancements.py`
- `tests/test_policy_engine.py`

Minimum deliverable:

- Repository query that summarizes historical success/failure by pattern, algorithm, and data source.
- Planner or policy context that carries learning hints.
- Decision trace that records whether and how a hint influenced a policy decision.

Smallest safe implementation slice:

```text
Add a capped `learning_adjustment` for `pattern_selection` only, derived from durable summaries and emitted in candidate evidence. Add a test where seeded durable failures lower a pattern's policy score without changing KG seed data.
```

Verification:

- Unit tests for repository summaries.
- Planner/policy tests proving hints appear and are auditable.
- `python -m pytest -q`

Continue condition:

- Hints are explainable and do not create hidden mutable policy behavior.

Stop or pivot condition:

- If hints do not produce useful differentiating evidence, keep durable learning as audit evidence and defer auto-tuning.

## Phase E: Minimum Research Ontology Closure

Entry condition:

- Phase B identifies which ontology concepts are necessary for claims.
- Phase C/D evidence is stable enough that ontology changes will not mask core runtime gaps.

Current touchpoints:

- `kg/models.py`
- `kg/seed.py`
- `kg/source_catalog.py`
- `kg/repository.py`
- `kg/inmemory_repository.py`
- `kg/neo4j_repository.py`
- `kg/bootstrap/neo4j_bootstrap.cypher`
- `tests/test_kg_repository_enhancements.py`
- `tests/test_neo4j_bootstrap.py`
- `tests/test_neo4j_repository.py`

Minimum deliverable:

- One minimal concept family, likely `OutputRequirement`, `QoSPolicy`, or deeper `ScenarioProfile`, implemented across in-memory repository, Neo4j bootstrap, planner context, and tests.

Smallest safe implementation slice:

```text
Add `list_data_types`, include `data_types` in `KGContext` and planner retrieval, and add `tests/test_ontology_closure.py` to validate all in-memory seed references resolve.
```

Verification:

- `tests/test_kg_repository_enhancements.py`
- `tests/test_neo4j_bootstrap.py`
- `tests/test_planner_context.py`
- `python -m pytest -q`

Continue condition:

- The new concept enters planner/runtime evidence, not only static docs.

Stop or pivot condition:

- If the concept cannot affect retrieval, planning, validation, or policy, keep it in research ontology docs and avoid expanding code.

## Phase F: One New Data/Task Vertical Slice

Entry condition:

- Core claims are stable enough to test extensibility.
- Phase B chooses the extension target.

Current touchpoints:

- `schemas/fusion.py`
- `agent/executor.py`
- `kg/seed.py`
- `kg/source_catalog.py`
- `adapters/building_adapter.py`
- `adapters/road_adapter.py`
- `Algorithm/water_polygon.py`
- `Algorithm/water_line.py`
- `tests/golden_cases`

Minimum deliverable:

- Exactly one new vertical slice beyond the current center.
- Candidate choices: `raw.google.building` automatic materialization if feasible, or a controlled `water`/`POI` vector slice if Google automation is blocked.
- Source catalog metadata, materialization behavior, bundle assembly, tests, and at least one smoke or harness path.

Smallest safe implementation slice:

```text
Add an uploaded-input-only `water` polygon slice first: `JobType.water`, `adapters/water_adapter.py`, `algo.fusion.water.polygon.safe`, `wp.flood.water.safe`, `dt.water.bundle`, `dt.water.fused`, `osp.water.fused.v1`, executor handler, one adapter unit test, one planner context test, one v2 uploaded API integration test, and one golden case.
```

Verification:

- Source-specific unit tests.
- Focused runtime/API tests.
- One manifest or smoke command with saved output.
- `python -m pytest -q`

Continue condition:

- The slice proves architecture extensibility without creating broad manual setup requirements.

Stop or pivot condition:

- If provider licensing, download mechanics, or data quality block automation, switch to a more controlled vertical slice instead of forcing the provider.

## Phase G: Experiment Matrix + Paper Evidence Freeze

Entry condition:

- Claims, core runtime behavior, and extension target are stable.

Minimum deliverable:

- Frozen experiment matrix with baselines, metrics, datasets, run commands, expected artifacts, and result storage paths.
- Paper-ready tables or structured JSON summaries.
- Explicit failure-case analysis.

Verification:

- Full targeted tests.
- Required harness or benchmark runs.
- Evidence paths cross-check back to `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, and artifact bundles.

Continue condition:

- Results are sufficient for thesis/paper claims.

Stop or pivot condition:

- If evidence is insufficient, return only to the weakest earlier phase instead of opening unrelated features.

## Phase H: Thin Productization / Operator Surface

Entry condition:

- Phase G evidence is frozen or nearly frozen.
- The final deliverable requires a product-facing demonstration layer.

Current touchpoints:

- `api/routers/runs_v2.py`
- `schemas/agent.py`
- `services/agent_run_service.py`
- `worker/tasks.py`
- `worker/celery_app.py`
- `docs/v2-operations.md`
- `tests/test_api_v2_integration.py`
- `tests/test_worker_orchestration.py`

Minimum deliverable:

- A thin operator workflow around existing endpoints: run creation, inspection, artifact download, comparison, retry/cancel if implemented.
- This can be API-first or a small dashboard; it should not become a large product rewrite.

Smallest safe implementation slice:

```text
Add `GET /api/v2/runs` with `phase`, `job_type`, and `limit` filters backed by persisted `run.json` scanning, plus `RunListResponse` and one API test. This gives operator discovery without touching core execution.
```

Verification:

- Smoke test for the operator workflow.
- Documentation update in `docs/v2-operations.md`.
- `python -m pytest -q`

Continue condition:

- The surface helps demonstrate or operate the system without diluting research evidence work.

Stop or pivot condition:

- If product UI work threatens paper deadlines, keep API/operator docs as the productization boundary.

## Current Recommendation

After Phase A, proceed to Phase B. Do not start Phase C before Phase B freezes the claims and evaluation contract. The highest-value chain today is:

```text
A -> B -> C -> D
```

Then decide whether E, F, G, and H remain necessary based on evidence and deadline pressure.
