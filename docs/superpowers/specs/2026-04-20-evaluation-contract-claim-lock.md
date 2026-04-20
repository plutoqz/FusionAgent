# Evaluation Contract And Thesis Claim Lock

## Purpose

This document locks the claims FusionAgent is allowed to pursue in the next implementation chain. It prevents the project from claiming more than the current evidence supports, and it defines the metrics and baselines needed before later phases can be treated as thesis-grade evidence.

## Claim Disposition Legend

- `in_scope_now`: current implementation plus existing evidence can support the claim after final benchmark/evidence freeze.
- `requires_next_phase`: claim is important, but the next implementation phase must create missing evidence or behavior.
- `conditional`: keep the claim only if earlier gates confirm it is needed for the final paper/product target.
- `boundary_only`: document as a limitation or future product target, not as a current contribution.

## Locked Claim Map

| ID | Claim | Disposition | Proof Type | Metrics | Required Baselines | Current Evidence | Missing Evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| C1 | FusionAgent can generate executable geospatial fusion workflows through KG-constrained planning and validation | in_scope_now | Tests plus harness summaries plus plan/audit artifacts | planning_validity_rate, decision_trace_completeness | full_system, kg_top_pattern_only, weak_llm_without_runtime_constraints | Planner, validator, policy, API, and harness tests exist | Final run matrix must archive plan and validation artifacts |
| C2 | FusionAgent produces auditable execution evidence for each run | in_scope_now | Run artifact inspection and API evidence | evidence_completeness_rate, artifact_validity | full_system | `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, artifact bundle are documented and tested | Final evidence freeze must trace every benchmark row to raw run artifacts |
| C3 | FusionAgent improves robustness through reactive healing and full replan V1 | requires_next_phase | Fault-injection tests and ablation comparison | recovery_success_rate, execution_success_rate, decision_trace_completeness | full_system, no_repair_or_replan | Current executor has repair/fallback and run service has partial replan retry | Phase C must prove downstream re-entry, plan revision evidence, and explicit acceptance gates |
| C4 | Durable learning can influence future planning or policy in an auditable way | requires_next_phase | Deterministic policy-hint tests and decision traces | decision_trace_completeness, recovery_success_rate, planning_validity_rate | full_system, no_durable_learning_hints | Durable records and aggregate summaries exist | Phase D must add explicit learning hints or scoped policy adjustments |
| C5 | Task-driven AOI and source acquisition reduce manual input preparation for bounded official sources | in_scope_now | Source materialization tests plus real-data benchmark | reproducibility_status, execution_success_rate, runtime_duration_ms | full_system, manual_input_baseline | Fresh-checkout Microsoft building benchmark and source asset tests exist | Final benchmark should rerun and archive direct summary JSON |
| C6 | Executable ontology and research ontology are aligned enough to support the paper narrative | conditional | KG seed/query tests and ontology closure checks | planning_validity_rate, decision_trace_completeness | full_system | Current docs distinguish executable subset and target ontology | Phase E should only proceed if Phase B/G needs stronger ontology evidence |
| C7 | FusionAgent architecture can extend beyond building/road | conditional | One new vertical-slice benchmark | planning_validity_rate, execution_success_rate, artifact_validity | full_system | Current runtime is strong for building/road; water algorithms exist but are not adapterized | Phase F should implement exactly one extra vertical slice if evidence demands extensibility proof |
| C8 | FusionAgent has a usable operator-facing product surface | boundary_only | Operator API smoke and product demo evidence | evidence_completeness_rate, artifact_validity | full_system | Inspection and comparison endpoints exist | A full UI, auth, retention, listing, retry/cancel, and observability are product future work unless Phase H is activated |

## Phase C Decision

Full Replan Loop V1 is required before FusionAgent can make a strong robustness claim beyond bounded repair/fallback behavior.

The current repository already has useful repair and partial replan evidence. The missing proof is not "any replan function exists"; the missing proof is that a failed plan revision can re-enter downstream runtime stages safely, preserve old/new plan evidence, refresh task-driven inputs or reuse decisions when source/type changes, and record why the revised plan was accepted or rejected.

Therefore:

```text
Phase C is authorized as the next implementation phase after Phase B.
```

## Phase D Decision

Durable learning is important, but it should not become speculative auto-tuning. Phase D is authorized only as a narrow policy-hint slice after Phase C is stable.

The first acceptable implementation target is:

```text
Add a capped, explainable learning adjustment for one decision type, preferably pattern_selection, and record the adjustment in candidate evidence.
```

## Metrics Contract

| Metric | Definition | Source | Required For |
| --- | --- | --- | --- |
| planning_validity_rate | Percentage of generated plans that pass workflow validation without manual repair | harness summary, validation artifacts | C1, C6, C7 |
| execution_success_rate | Percentage of runs that reach succeeded status and produce a valid artifact bundle | harness summary, run status | C1, C3, C5, C7 |
| recovery_success_rate | Percentage of injected failures that recover through repair or replan | fault-injection tests and harness variants | C3, C4 |
| evidence_completeness_rate | Percentage of runs with `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, and artifact bundle | run directories, inspection endpoint | C2, C8 |
| reproducibility_status | Whether the case can run from tracked source ids or documented external providers without restored local-only data | manifest and source materialization output | C5 |
| runtime_duration_ms | Run duration in milliseconds, split by case and runtime mode | harness summary | C5, C7 |
| artifact_validity | Whether output artifact contains expected shapefile members and readable vector data | harness, smoke scripts, adapter tests | C2, C7, C8 |
| decision_trace_completeness | Whether key decisions include selected id, candidates, metrics, metadata, and rationale | `run.json`, audit, policy tests | C1, C3, C4, C6 |

## Baseline Matrix

| Baseline | Purpose | Feasibility Now | Implementation Need |
| --- | --- | --- | --- |
| full_system | Main FusionAgent runtime with planner, validator, policy, executor, repair, audit, and writeback | executable now | Existing tests and harness |
| kg_top_pattern_only | Shows value of LLM/contextual planning over deterministic top retrieval | partially executable with a harness/planner switch | Phase G or earlier ablation switch |
| weak_llm_without_runtime_constraints | Shows value of KG and validator constraints | narrative now | Needs controlled planner variant; keep out of hard claims until implemented |
| no_repair_or_replan | Shows value of healing and replan | requires Phase C | Add fault-injection harness mode or test-only runtime switch |
| no_durable_learning_hints | Shows value of Phase D hints | requires Phase D | Compare decisions with and without learning adjustment |
| manual_input_baseline | Shows value of task-driven acquisition | executable as documented contrast | Compare uploaded/local bundle path with source-id materialization path |

## Evaluation Tiers

### Tier 1: Targeted Tests

Use for everyday regression:

```powershell
python -m pytest -q
```

Focused runtime/evidence subset:

```powershell
python -m pytest -q tests/test_eval_harness.py tests/test_api_v2_integration.py tests/test_agent_run_service_enhancements.py
```

### Tier 2: Golden-Case Harness

Use for API-to-runtime closed-loop confidence:

```powershell
python scripts/eval_harness.py `
  --base-url http://127.0.0.1:8000 `
  --timeout 180 `
  --case building_disaster_flood `
  --case road_disaster_earthquake `
  --output-json tmp/eval/fast-confidence-summary.json
```

Expected evidence:

- harness summary JSON
- `case_id`
- `run_id`
- status and artifact checks

### Tier 3: Real-Data Benchmark

Use for paper-grade real-data evidence:

```powershell
python scripts/eval_harness.py `
  --manifest docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json `
  --case building_gitega_micro_msft_agent `
  --base-url http://127.0.0.1:8010 `
  --timeout 1200 `
  --output-json tmp/eval/fresh-checkout-micro-msft.json
```

Before running clean-checkout real-data evidence, prefetch bounded official assets when needed:

```powershell
python scripts/materialize_source_assets.py `
  --source raw.osm.building `
  --source raw.microsoft.building `
  --bbox 29.817351,-3.646572,29.931113,-3.412421 `
  --prefer-remote
```

Expected evidence:

- summary JSON
- `run_id`
- matching run directory containing `run.json`, `plan.json`, `validation.json`, `audit.jsonl`
- artifact bundle
- runtime metadata from `/api/v2/runtime`

### Tier 4: Fault-Injection And Ablation Matrix

Use after Phase C/D implementation:

- source unavailable
- source clips to empty
- schema/field issue
- algorithm execution failure
- no-repair/no-replan variant
- no-learning-hints variant

Expected evidence:

- old plan and new plan or explicit fail reason
- repair/replan decision record
- final status
- candidate evidence showing whether learning hints influenced policy

## Evidence Tracking Rules

Track in git:

- claim/evaluation specs
- benchmark manifest files
- curated summary JSON intended for paper evidence
- small tables or matrices used in the thesis

Do not track by default:

- raw `runs/` directories
- source caches under `runs/source-assets/`
- large artifact bundles
- external provider downloads

When a raw run artifact is needed for paper evidence, record:

```text
run_id
commit_sha
base_url
runtime mode
command
summary JSON path
artifact storage location
```

## Next Authorized Work

Phase C is the next implementation phase.

The first Phase C plan should target the smallest safe replan improvement:

```text
After `replan_applied`, re-run input acquisition when `input_strategy=task_driven_auto` and the selected source or required input type changed. Preserve old and new plan evidence and add a focused regression test.
```

Phase D remains queued after Phase C:

```text
Add a capped learning adjustment for one decision type and emit it in candidate evidence.
```

Phase E-H remain conditional and should not start before Phase C/D evidence is reviewed.
