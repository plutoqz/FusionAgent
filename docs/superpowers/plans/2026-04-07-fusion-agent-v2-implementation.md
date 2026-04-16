# FusionAgent V2 Master Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn FusionAgent from a runnable and auditable MVP into a research-grade, policy-driven, continuously verifiable disaster fusion agent with a stable evaluation and evidence loop.

**Architecture:** Keep the current single-agent runtime centered on `services/agent_run_service.py`. Continue evolving the system through six controlled layers: evaluation and evidence, search-space expansion, policy coverage, artifact reuse, long-term writeback, and productization. Use this file as the single source of truth for roadmap status and next actions.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic, pytest, GeoPandas, Neo4j or in-memory KG, local JSON registries, local runtime scripts, markdown and JSON evidence artifacts

---

## Plan Usage

This file is the master plan and progress tracker.

- Read this file first before planning or implementation.
- Update this file when a task starts, completes, is descoped, or is replaced.
- Keep completed tasks here unless they are pure noise; they are part of the project history.
- Prefer updating this file over creating a parallel plan.
- If a phase needs highly detailed execution notes, create a supporting doc under `docs/superpowers/plans/` and link it here, but keep the status and phase gate in this file.

## Status Legend

- `[x]` completed and verified
- `[ ]` not started or intentionally reopened

## Current Snapshot

**Last updated:** `2026-04-16`

**Overall judgment:** FusionAgent has already crossed the "basic runtime MVP" line, and the current V2 roadmap is now complete for its intended scope. The primary remaining work is no longer closing baseline roadmap gaps; it is defining the next research and product iteration without losing the evidence discipline and runtime transparency established in this phase.

**What is already in place:**

- [x] `planner -> validator -> executor/healing -> writeback` runtime loop is implemented in `services/agent_run_service.py`
- [x] Explicit `PolicyEngine` v1 exists in `agent/policy.py`
- [x] KG-backed parameter default binding exists in `agent/parameter_binding.py`
- [x] Persistent artifact registry exists in `services/artifact_registry.py`
- [x] Runtime artifact direct reuse and clip reuse exist in `services/artifact_reuse_service.py`
- [x] Audit trail and decision records are persisted through the run lifecycle
- [x] Evaluation harness exists in `scripts/eval_harness.py`
- [x] Benchmark timeout misdiagnosis was corrected and follow-up evidence was recorded in `docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md`
- [x] Benchmark evidence now records runtime-aligned metadata through `/api/v2/runtime`, and the latest clean micro rerun is tracked in `docs/superpowers/specs/2026-04-16-building-micro-alignment-result.json`

**What still needs deliberate follow-on planning:**

- [x] Evaluation and benchmark evidence are now handled through a documented, runtime-aligned workflow for the current repo-supported benchmark cases
- [x] Search-space expansion, policy coverage, artifact reuse hardening, long-term writeback, and operator inspection reached the completion bar defined by this roadmap
- [ ] Fresh-checkout reproducibility still depends on restoring the local `Data/` assets or repointing manifests to equivalent tracked inputs
- [ ] Broader disaster/theme coverage, stronger CI evidence automation, and richer operator UX should be treated as a new roadmap rather than unfinished checklist items from this V2 plan

## Supporting Documents

- Spec: `docs/superpowers/specs/2026-04-07-fusion-agent-v2-design.md`
- Progress summary: `docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md`
- Historical implementation plan: this file, now promoted to the master tracker
- Historical focused plan: `docs/superpowers/plans/2026-04-08-fusion-agent-parameter-defaults-and-building-benchmark.md`
- Historical benchmark follow-up plan: `docs/superpowers/plans/2026-04-08-benchmark-followup-and-runtime-alignment.md`

## Roadmap Order

The project should advance in this order unless a blocker or research requirement forces a deviation:

- Phase 1: Evaluation and evidence hardening
- Phase 2: Search-space expansion
- Phase 3: Policy coverage expansion
- Phase 4: Artifact reuse v2
- Phase 5: Long-term writeback and learning loop
- Phase 6: Productization and operations

The intended rule is simple: do not spend major effort on product polish until the evaluation loop, search space, and policy story are good enough to support repeatable research iteration.

---

## Phase 0: Completed Foundation

This phase is already done enough to treat as baseline, not open work.

### Completed Runtime Capabilities

- [x] `RunStatus`, `DecisionRecord`, `ArtifactReuseDecision`, repair records, and audit event persistence
- [x] Initial planning and replanning with plan revision tracking
- [x] Parameter defaults bound from KG specs into executable task inputs
- [x] Candidate pattern retrieval and planner context enrichment
- [x] Deterministic weighted policy scoring for current runtime decisions
- [x] Runtime artifact registration after success
- [x] Direct artifact reuse for exact spatial match
- [x] Clip-based artifact reuse for contained AOI reuse
- [x] Fallback from failed reuse materialization to fresh execution
- [x] Golden-case and manifest-backed evaluation harness
- [x] Benchmark correction workflow and follow-up summary

### Baseline Verification Evidence

- [x] Targeted policy, planner reuse, harness, and runtime enhancement tests were passing on `2026-04-09`
- [x] Targeted API v2, planner context, and parameter binding tests were passing on `2026-04-09`

### Carry-Forward Cleanup Items

- [x] Update wording drift where planner-stage artifact reuse rationale still claims no runtime short-circuit even though runtime short-circuit now exists
- [x] Re-sync README, runtime docs, and benchmark summaries for the `2026-04-16` evidence-hardening closure batch

---

## Phase 1: Evaluation And Evidence Hardening

**Intent:** Make benchmark and validation output trustworthy enough that future architecture and policy work can be judged with evidence instead of anecdotes.

**Exit criteria:**

- Each benchmark result records enough metadata to explain what was run, where it ran, and why the result is credible.
- Harness defaults separate quick regression checks from long-running real-data benchmark runs.
- Timeout policy is explicit and encoded in inputs or manifests instead of hidden in operator memory.
- The repo has one documented path to run "fast confidence checks" and one documented path to run "real benchmark evidence."

### Files Likely To Change

- `scripts/eval_harness.py`
- `tests/test_eval_harness.py`
- `docs/v2-operations.md`
- `README.md`
- `docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md`
- `docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json`
- `.github/workflows/*` if a benchmark-safe CI split is added

### Task 1.1: Define Evaluation Tiers And Runtime Rules

- [x] Add a short section to `README.md` that defines three evaluation tiers: unit and targeted runtime tests, golden-case harness runs, and real-data benchmark runs.
- [x] Add a short section to `docs/v2-operations.md` that defines when to use each tier and what evidence must be saved.
- [x] Record the current timeout guidance in repo docs instead of only in ad hoc thread summaries.
- [x] State clearly that real-data building benchmarks are not expected to fit the current `180s` default timeout.
- [x] Add a "runtime alignment checklist" subsection covering API port, worker freshness, output directory alignment, and dependency file alignment.

### Task 1.2: Harden Harness Result Schema

- [x] Extend `scripts/eval_harness.py` summary output to include commit SHA when available.
- [x] Extend `scripts/eval_harness.py` summary output to include `base_url`, `timeout_sec`, and the command mode used (`golden-case` or `manifest`).
- [x] Extend `scripts/eval_harness.py` summary output to include a stable `environment` block with at least KG backend, LLM provider, and eager mode when available.
- [x] Add tests in `tests/test_eval_harness.py` that verify these fields are present in both directory-backed and manifest-backed summary modes.
- [x] Keep the summary JSON backward compatible by adding fields instead of renaming existing ones.

### Task 1.3: Encode Timeout Policy Instead Of Remembering It

- [x] Add optional per-case timeout support to manifest-driven evaluation in `scripts/eval_harness.py`.
- [x] Keep the CLI `--timeout` flag as the global default, but let manifest entries override it for known slow cases.
- [x] Add tests showing that a case-level timeout overrides the CLI default only for that case.
- [x] Update the real-data manifest and follow-up summary docs to use explicit timeout values for real building cases.
- [x] Avoid adding any dynamic timeout heuristics; keep this deterministic and inspectable.

### Task 1.4: Add Preflight Checks For Benchmark Credibility

- [x] Add a small preflight routine in `scripts/eval_harness.py` for manifest mode that checks API reachability before spending a long timeout window.
- [x] Add a preflight check that the referenced local shapefile inputs exist before the run starts.
- [x] Add tests that these failures return immediate, specific errors instead of generic timeouts.
- [x] Document the preflight behavior in `docs/v2-operations.md`.

### Task 1.5: Separate Fast Regression From Slow Evidence

- [x] Define and document a recommended "fast confidence" command that runs targeted pytest plus a narrow harness subset.
- [x] Define and document a recommended "real evidence" command that runs manifest-backed benchmark cases with longer timeouts.
- [x] If CI is updated, keep slow benchmarks out of default PR gating unless they are intentionally requested.
- [x] Make sure the commands are discoverable from `README.md` and `docs/v2-operations.md`.

### Task 1.6: Close Documentation Drift

- [x] Update `README.md` so the artifact reuse section reflects the actual runtime behavior.
- [x] Update any stale plan or design wording that claims artifact reuse is planner-only or non-short-circuiting.
- [x] Add one concise note in the master spec or summary that distinguishes current implemented behavior from target-state aspirations.

### Phase 1 Verification

- [x] Run `python -m pytest -q tests/test_eval_harness.py`
- [x] Run `python -m pytest -q tests/test_api_v2_integration.py tests/test_agent_run_service_enhancements.py`
- [x] Run one documented fast confidence command end-to-end and save the output path in this file
- [x] Run one manifest-backed real benchmark command end-to-end and record the output path in this file

### Phase 1 Completion Notes

- [x] Add completion date here when done
- [x] Add evidence file paths here when done
- [x] Add any follow-on issues that Phase 1 uncovered here when done

Current evidence and blockers:

- `2026-04-09`: targeted verification passed with `python -m pytest -q tests/test_eval_harness.py` and `python -m pytest -q tests/test_api_v2_integration.py tests/test_agent_run_service_enhancements.py`
- `2026-04-09`: `python -m pytest -q tests/test_local_smoke_helpers.py` passed after adding a regression test that proves smoke HTTP requests now respect the case timeout budget
- `2026-04-09`: documented fast confidence command passed end-to-end; summary saved to `tmp/eval/fast-confidence-summary.json`
- `2026-04-09`: documented real evidence command passed end-to-end after restoring `E:\vscode\fusionAgent\Data`; summary saved to `tmp/eval/real-evidence-summary.json`
- `2026-04-09`: successful real-data building case `building_gitega_osm_vs_google_agent` recorded run id `92fa35b6f1014d67a8e15fe2a1fe5db3`, duration `592549 ms`, and artifact size `28698170`
- `2026-04-09`: `building_gitega_osm_vs_msft_clipped_agent` remains intentionally skipped because the manifest still marks it `agent-ready-with-prep`
- `2026-04-16`: targeted evidence-hardening verification passed with `python -m pytest -q tests/test_eval_harness.py tests/test_api_v2_integration.py`
- `2026-04-16`: a clean isolated runtime on `http://127.0.0.1:8010` returned `/api/v2/runtime` metadata and passed both `python scripts/smoke_local_v2.py --base-url http://127.0.0.1:8010 --timeout 180` and the manifest-backed micro rerun saved to `docs/superpowers/specs/2026-04-16-building-micro-alignment-result.json` with run id `7117ef6fd95a44aa97d438cb7b3a9bee`

Follow-on issues uncovered in Phase 1:

- Road golden cases had stale `pattern_hint` values (`wp.flood.road`) and were updated to the concrete runtime pattern id `wp.flood.road.default`
- `utils/local_smoke.py` had a hidden fixed `30s` HTTP timeout that ignored the case-level benchmark timeout; this is now fixed and covered by `tests/test_local_smoke_helpers.py`
- Real-data manifest paths still depend on local shapefile assets outside git; Phase 1 now has a working evidence path again, but future fresh checkouts still need data restore or manifest repointing

---

## Phase 2: Search-Space Expansion

**Intent:** Increase the number and diversity of valid choices available to the planner and policy layers so the system evolves from a narrow workflow runner into a real decision-making fusion agent.

**Exit criteria:**

- Candidate patterns and supporting metadata are broad enough that policy selection is meaningful.
- The KG contains richer algorithm, source, and parameter metadata for at least the current building and road scopes.
- Search-space expansion remains constrained and auditable; no uncontrolled ontology sprawl.

### Files Likely To Change

- `kg/models.py`
- `kg/seed.py`
- `kg/repository.py`
- `kg/inmemory_repository.py`
- `kg/neo4j_repository.py`
- `kg/bootstrap.py`
- `agent/retriever.py`
- `agent/planner.py`
- `tests/test_kg_parameter_specs.py`
- `tests/test_kg_repository.py`
- `tests/test_kg_repository_enhancements.py`
- `tests/test_planner_context.py`
- `docs/superpowers/specs/2026-04-07-fusion-agent-v2-design.md`

### Task 2.1: Expand Disaster And Pattern Coverage Within Current Themes

- [x] Add additional disaster-specific workflow patterns for the existing `building` scope.
- [x] Add additional disaster-specific workflow patterns for the existing `road` scope.
- [x] Keep additions bounded to scenarios that can be represented and tested with current runtime architecture.
- [x] Add tests that retrieval returns multiple candidate patterns where policy choice is supposed to matter.
- [x] Document which new patterns are real runtime candidates versus target-state placeholders.

### Task 2.2: Enrich Algorithm Metadata

- [x] Add richer per-algorithm metadata for expected accuracy, stability, and intended usage mode where the data is trustworthy enough to encode.
- [x] Keep metadata deterministic and explicit in seed or repository-backed records.
- [x] Do not invent fake precision; if a metric is unknown, leave it absent rather than pretending.
- [x] Add tests that policy inputs can be assembled from this richer metadata without breaking old behavior.

### Task 2.3: Enrich Data Source Metadata

- [x] Expand `DataSource` coverage to include clearer freshness, quality, and supported-type signals.
- [x] Add tests that retriever context exposes the richer source metadata in a stable shape.
- [x] Decide on one conservative schema for source quality metadata and keep it consistent across in-memory and Neo4j backends.

### Task 2.4: Strengthen Parameter Spec Coverage

- [x] Review current KG parameter specs and fill obvious missing defaults for current supported algorithms.
- [x] Add spec metadata that supports future policy reasoning without forcing speculative tuning now.
- [x] Keep parameter binding deterministic; the planner should not guess missing defaults that belong in KG metadata.

### Task 2.5: Add Output Schema Policy Metadata

- [x] Introduce metadata needed to reason about output-field retention, renaming, or compatibility policy.
- [x] Keep this as metadata first; do not bury it inside adapters as implicit one-off logic.
- [x] Add tests that planner or retriever context can expose this metadata without changing runtime output behavior yet.

### Phase 2 Verification

- [x] Run `python -m pytest -q tests/test_kg_parameter_specs.py tests/test_kg_repository.py tests/test_kg_repository_enhancements.py`
- [x] Run `python -m pytest -q tests/test_planner_context.py tests/test_policy_engine.py`
- [x] Add one short note here summarizing how candidate breadth changed

Phase 2 note: candidate breadth now includes earthquake-specific building patterns and typhoon-specific road patterns; KG now exposes richer algorithm/data-source metadata, full current safe-mode parameter spec coverage with `tunable` and `optimization_tags`, and metadata-only output schema policies through in-memory retrieval, planner context, and Neo4j bootstrap output.

---

## Phase 3: Policy Coverage Expansion

**Intent:** Move from a partial explicit policy layer to a consistent policy system that explains major runtime choices instead of leaving them implicit.

**Exit criteria:**

- Decision records cover more than pattern selection and replan/fail.
- Runtime audit can explain why a source, parameter set, reuse path, or fallback path was chosen.
- Policy inputs and outputs are stable enough to benchmark.

### Files Likely To Change

- `agent/policy.py`
- `agent/retriever.py`
- `agent/planner.py`
- `services/agent_run_service.py`
- `schemas/agent.py`
- `tests/test_policy_engine.py`
- `tests/test_agent_run_service_enhancements.py`
- `tests/test_planner_context.py`

### Task 3.1: Add Explicit Decision Types

- [x] Add `data_source_selection` decision support.
- [x] Add `artifact_reuse_selection` decision support.
- [x] Add `parameter_strategy` or equivalent decision support for parameter-level choices that are policy driven rather than static defaults.
- [x] Add `output_schema_policy` decision support if output compatibility policy becomes executable in this phase.

### Task 3.2: Standardize Candidate Evidence

- [x] Define one stable candidate evidence shape so every decision type can emit comparable traces.
- [x] Keep rationale strings concise but evidence-backed.
- [x] Prefer additive schema evolution in `schemas/agent.py`.

### Task 3.3: Wire Policy Decisions Into Runtime Status

- [x] Ensure new decision types are persisted into `RunStatus` and audit events.
- [x] Ensure failure and fallback paths still preserve prior decision history instead of overwriting it.
- [x] Add tests that multiple decision types can coexist in the same run.

### Phase 3 Verification

- [x] Run `python -m pytest -q tests/test_policy_engine.py tests/test_agent_run_service_enhancements.py`
- [x] Run at least one end-to-end run and inspect `audit.jsonl` and `run.json`
- [x] Add a short summary here of which decision types are now explicit

Phase 3 note: explicit runtime decision coverage now includes `pattern_selection`, `data_source_selection`, `artifact_reuse_selection`, `parameter_strategy`, `output_schema_policy`, and `replan_or_fail`, with every candidate carrying the same `metrics + meta` evidence shape in both `run.json` and audit-backed status updates.

---

## Phase 4: Artifact Reuse V2

**Intent:** Upgrade artifact reuse from a useful first pass into a stronger, compatibility-aware reuse subsystem that can support real claims about freshness and correctness.

**Exit criteria:**

- Reuse decisions consider more than recency and bounding box containment.
- Reuse failures are diagnosable and policy-aware.
- Direct and clip reuse remain fast paths, but their safety rules are clearer and better tested.

### Files Likely To Change

- `services/artifact_registry.py`
- `services/artifact_reuse_service.py`
- `services/agent_run_service.py`
- `agent/retriever.py`
- `agent/policy.py`
- `tests/test_artifact_registry.py`
- `tests/test_planner_artifact_reuse.py`
- `tests/test_agent_run_service_enhancements.py`

### Task 4.1: Improve Compatibility Checks

- [x] Add schema compatibility checks beyond raw field subset matching where practical.
- [x] Add CRS-aware handling rules or explicitly reject unsafe cross-CRS reuse paths.
- [x] Add provenance metadata needed to explain why a record was considered reusable.

### Task 4.2: Add Freshness Policy By Work Type

- [x] Stop treating all artifacts as having the same acceptable age.
- [x] Define a conservative freshness policy keyed by job type and, if justified, scenario type.
- [x] Keep the rule table explicit and test-backed.

### Task 4.3: Add Stronger Quality Gates

- [x] Add validation for clip outputs that would otherwise silently produce misleading artifacts.
- [x] Keep failure behavior explicit: reject or fall back, never silently degrade.
- [x] Add tests for empty clips, mismatched schema, stale artifacts, and unsafe compatibility cases.

### Phase 4 Verification

- [x] Run `python -m pytest -q tests/test_artifact_registry.py tests/test_planner_artifact_reuse.py tests/test_agent_run_service_enhancements.py`
- [x] Add one direct reuse run and one clip reuse run to evidence notes if practical

Phase 4 note: artifact reuse now requires compatible `output_data_type` and `target_crs`, carries explicit provenance metadata into the registry and planner retrieval, uses job-type freshness windows (`building=3d`, `road=1d`), and validates clip outputs for CRS, required fields, and bbox safety before short-circuiting fresh execution.

---

## Phase 5: Long-Term Writeback And Learning Loop

**Intent:** Distinguish transient run logging from durable learning so that successful and failed runs can influence future planning and policy in a controlled way.

**Exit criteria:**

- The system has an explicit boundary between runtime logs and durable learning records.
- Aggregated execution evidence can be queried without replaying raw audit logs.
- Policy tuning and reuse heuristics can reference durable evidence instead of only seed metadata.

### Files Likely To Change

- `services/agent_run_service.py`
- `kg/models.py`
- `kg/repository.py`
- `kg/inmemory_repository.py`
- `kg/neo4j_repository.py`
- `agent/retriever.py`
- `tests/test_kg_repository_enhancements.py`
- `tests/test_repair_audit.py`

### Task 5.1: Define Durable Learning Records

- [x] Define the minimal durable evidence entities needed for future planning and policy.
- [x] Keep them separate from verbose audit logs.
- [x] Add tests for storing and reading them across backends.

### Task 5.2: Aggregate Run Outcomes

- [x] Add a path to aggregate repeated run outcomes by pattern, algorithm, and scenario slice.
- [x] Keep writeback deterministic and append-only where possible.
- [x] Avoid premature auto-tuning; start by storing evidence cleanly.

### Task 5.3: Expose Durable Evidence To Retrieval

- [x] Feed aggregated evidence into planner or policy retrieval only after the storage shape is stable.
- [x] Add tests that retrieval can surface the evidence without breaking existing context contracts.

### Phase 5 Verification

- [x] Run repository enhancement tests
- [x] Run targeted planner or retriever tests
- [x] Add one note here describing what evidence is now durable

Phase 5 note: every run now writes a compact `DurableLearningRecord` summary separate from audit logs, repositories can aggregate those records into pattern/algorithm/data-source outcome summaries by scenario slice, and planner retrieval now surfaces that durable evidence without replaying raw `audit.jsonl`.

---

## Phase 6: Productization And Operations

**Intent:** Build the operator-facing layer only after the engine beneath it is reliable enough to justify long-lived UX and deployment investment.

**Exit criteria:**

- Operators can inspect runs, plans, decisions, and artifacts without reading raw files by hand.
- Deployment and runtime lifecycle are documented and repeatable.
- Productization does not hide the research evidence trail.

### Files Likely To Change

- `api/routers/*`
- `services/*`
- `docs/v2-operations.md`
- `README.md`
- any future frontend workspace if one is introduced

### Task 6.1: Operator Inspection Flow

- [x] Design a run inspection flow that surfaces status, plan, audit, and artifact in one place.
- [x] Keep the first version narrow and operational, not flashy.

### Task 6.2: Run Comparison And Audit Review

- [x] Add a way to compare runs or benchmark outputs at the product layer.
- [x] Preserve access to raw evidence instead of replacing it with summary-only UI.

### Task 6.3: Deployment And Runtime Hygiene

- [x] Harden startup, logging, retention, and local versus managed runtime conventions.
- [x] Document production-like runtime expectations separately from quick local development mode.

### Phase 6 Verification

- [x] Define product-layer acceptance checks once the phase becomes active

Phase 6 note: the v2 API now exposes a one-shot inspection endpoint and a side-by-side compare endpoint for run review, while `docs/v2-operations.md` now documents operator flows plus local-vs-managed runtime conventions without hiding the raw evidence files behind summary-only UI.

---

## Cross-Cutting Rules

- [ ] Do not add major new product surfaces before Phase 1, Phase 2, and Phase 3 are in acceptable shape.
- [ ] Do not widen the ontology unless the new metadata is usable by runtime, policy, or evaluation.
- [ ] Do not hide important decision logic inside prompts when it should be explicit and auditable.
- [ ] Do not treat benchmark success as credible without runtime alignment, timeout clarity, and saved evidence.
- [ ] After every meaningful phase, update `README.md`, this master plan, and any affected spec or summary docs together.

## Immediate Next Actions

These are the next items to work in order.

- [x] Phase 2 Task 2.1: expand disaster and pattern coverage within current `building` and `road` themes
- [x] Phase 2 Task 2.2: enrich algorithm metadata beyond bare success rate and alternatives
- [x] Phase 2 Task 2.3: enrich data source metadata and expose it stably in retrieval context
- [x] Phase 2 Task 2.4: strengthen parameter spec coverage for current supported algorithms
- [x] Phase 2 Task 2.5: add output schema policy metadata
- [x] Phase 3 Task 3.1: add explicit decision types beyond pattern selection and replan/fail
- [x] Phase 4 Task 4.1: improve artifact reuse compatibility checks
- [x] Phase 5 Task 5.1: define durable learning records
- [x] Phase 6 Task 6.1: design operator inspection flow
- [x] Revisit whether benchmark evidence should be copied out of `tmp/eval/` into a more durable tracked note or summary

## Progress Log

- `2026-04-07`: original V2 implementation plan created
- `2026-04-08`: benchmark follow-up plan and corrected benchmark summary added
- `2026-04-09`: master plan rewritten into a long-lived roadmap and progress tracker; current priority set to Phase 1 evaluation and evidence hardening
- `2026-04-09`: Phase 1 Task 1.1 completed in `codex/phase1-task1-1`; README and `docs/v2-operations.md` now define evaluation tiers, timeout guidance, and runtime alignment checklist
- `2026-04-09`: Phase 1 Task 1.2 completed in `codex/phase1-task1-1`; `scripts/eval_harness.py` summary now records commit SHA, command mode, `base_url`, `timeout_sec`, and environment metadata
- `2026-04-09`: Phase 1 Task 1.3 completed in `codex/phase1-task1-1`; manifest-backed evaluation now supports case-level `timeout_sec`, and the real-data building manifest encodes `1200` seconds explicitly
- `2026-04-09`: Phase 1 Task 1.4 completed in `codex/phase1-task1-1`; manifest mode now performs API and input preflight so configuration problems fail immediately with specific errors
- `2026-04-09`: Phase 1 Task 1.5 completed in `codex/phase1-task1-1`; README and `docs/v2-operations.md` now publish one recommended fast-confidence command and one recommended real-evidence command, while default CI remains on the fast pytest-only lane
- `2026-04-09`: Phase 1 Task 1.6 completed in `codex/phase1-task1-1`; README, the master plan, and the V2 design spec now state clearly that runtime direct/clip reuse short-circuit already exists and Phase 4 is about strengthening it rather than introducing it
- `2026-04-09`: Phase 1 verification passed for targeted pytest and the documented fast-confidence command; the documented real-evidence command now fails fast with a specific missing-input preflight error instead of a long opaque timeout
- `2026-04-09`: Phase 1 completed in `codex/phase1-task1-1`; local data was restored, `utils/local_smoke.py` was fixed to honor case-level timeouts end-to-end, and the documented real-evidence command succeeded for `building_gitega_osm_vs_google_agent`
- `2026-04-09`: Phase 2 Task 2.1 completed in `codex/phase1-task1-1`; KG seeds now include additional disaster-specific `building` and `road` runtime candidates, planner retrieval exposes pattern metadata, and retrieval tests confirm multiple candidate patterns are visible where policy choice should matter
- `2026-04-09`: Phase 2 verification for Task 2.1 passed in `codex/phase1-task1-1` with `python -m pytest -q tests/test_kg_parameter_specs.py tests/test_kg_repository.py tests/test_kg_repository_enhancements.py` and `python -m pytest -q tests/test_planner_context.py tests/test_policy_engine.py`
- `2026-04-09`: Phase 2 Tasks 2.2 and 2.3 completed in `codex/phase2-task2-2-2-3`; KG algorithms now carry explicit `accuracy_score`, `stability_score`, and `usage_mode`, data sources now expose stable freshness/quality/type signals plus broader earthquake-building and typhoon-road catalog coverage, and planner retrieval plus `CandidateScoreInput` can consume the richer metadata without changing old call shapes
- `2026-04-09`: Phase 2 verification for Tasks 2.2 and 2.3 passed in `codex/phase2-task2-2-2-3` with `python -m pytest -q tests/test_kg_parameter_specs.py tests/test_kg_repository.py tests/test_kg_repository_enhancements.py` and `python -m pytest -q tests/test_planner_context.py tests/test_policy_engine.py`
- `2026-04-09`: Phase 2 Tasks 2.4 and 2.5 completed in `codex/phase2-task2-2-2-3`; safe-mode building/road algorithms now have full current adapter parameter coverage, `AlgorithmParameterSpec` carries `tunable` and `optimization_tags`, and KG output schema policy metadata is exposed to planner retrieval without changing runtime output behavior
- `2026-04-09`: Phase 2 completed in `codex/phase2-task2-2-2-3`; verification passed with `python -m pytest -q tests/test_kg_parameter_specs.py tests/test_kg_repository.py tests/test_kg_repository_enhancements.py`, `python -m pytest -q tests/test_planner_context.py tests/test_policy_engine.py`, and `python -m pytest -q tests/test_parameter_binding.py`
- `2026-04-09`: Phase 3 Tasks 3.1 to 3.3 completed in `codex/phase3-task3-1`; planning now emits explicit `data_source_selection`, `artifact_reuse_selection`, `parameter_strategy`, and `output_schema_policy` decisions alongside existing `pattern_selection` and `replan_or_fail`, and every decision candidate now persists a stable `metrics + meta` evidence shape
- `2026-04-09`: Phase 3 completed in `codex/phase3-task3-1`; verification passed with `python -m pytest -q tests/test_agent_state_models.py tests/test_policy_engine.py tests/test_agent_run_service_enhancements.py`, `python -m pytest -q tests/test_planner_context.py`, and the end-to-end audit/run inspection embedded in `tests/test_agent_run_service_enhancements.py::test_agent_run_service_updates_status_and_records_feedback`
- `2026-04-09`: Phase 4 Tasks 4.1 to 4.3 completed in `codex/phase4-task4-1`; artifact reuse now filters on explicit `output_data_type` plus `target_crs`, records reuse provenance metadata in the registry, applies job-type freshness windows, and validates clip outputs before allowing short-circuit reuse
- `2026-04-09`: Phase 4 completed in `codex/phase4-task4-1`; verification passed with `python -m pytest -q tests/test_artifact_registry.py tests/test_planner_artifact_reuse.py tests/test_agent_run_service_enhancements.py` and `python -m pytest -q tests/test_planner_context.py`, while the direct-reuse and clip-reuse happy-path evidence remains covered by `tests/test_agent_run_service_enhancements.py`
- `2026-04-09`: Phase 5 Tasks 5.1 to 5.3 completed in `codex/phase5-task5-1`; runtime now writes compact durable learning summaries per run, repositories can aggregate them into pattern/algorithm/source evidence by disaster slice, and planner retrieval exposes those summaries in a stable shape
- `2026-04-09`: Phase 5 completed in `codex/phase5-task5-1`; verification passed with `python -m pytest -q tests/test_kg_repository_enhancements.py tests/test_neo4j_repository.py tests/test_planner_context.py tests/test_agent_run_service_enhancements.py`
- `2026-04-09`: Phase 6 Tasks 6.1 to 6.3 completed in `codex/phase6-task6-1`; the v2 API now exposes `/inspection` and `/compare` operator views, and `docs/v2-operations.md` was rewritten into a clean current-state runtime guide covering inspection, comparison, and local-vs-managed conventions
- `2026-04-09`: Phase 6 completed in `codex/phase6-task6-1`; verification passed with `python -m pytest -q tests/test_api_v2_integration.py`
- `2026-04-16`: benchmark evidence revisit closed; durable tracked summaries now live under `docs/superpowers/specs/`, and README plus runtime docs now record the standard local port and dependency conventions for `8000` default development, `8010` isolated benchmarks, and `8011` isolated fast-confidence runs
- `2026-04-16`: clean isolated runtime verification on `http://127.0.0.1:8010` showed that `building_gitega_micro_agent` now passes in current `main`; the earlier queued `2026-04-12` micro run is preserved as historical environment drift evidence rather than the current expected runtime state
- `2026-04-16`: evidence capture hardening improved again; the v2 API now exposes `/api/v2/runtime`, and `scripts/eval_harness.py` now prefers runtime-reported metadata over shell-only env capture when building benchmark summaries

## Self-Review

### Spec coverage

- Current runtime foundation is preserved and marked as completed baseline.
- Evaluation and evidence hardening is now the first active phase.
- Search-space expansion, policy expansion, artifact reuse strengthening, long-term writeback, and productization are all represented as later phases.

### Placeholder scan

- No `TODO`, `TBD`, or "similar to above" placeholders are left as execution steps.
- Later phases remain detailed enough to guide sequencing without pretending exact implementation details are already settled.

### Type consistency

- File paths referenced here match current repo structure.
- Phase order matches the intended dependency chain described in the roadmap section.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-07-fusion-agent-v2-implementation.md`.

Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Pick one when you want to move from planning into implementation.
