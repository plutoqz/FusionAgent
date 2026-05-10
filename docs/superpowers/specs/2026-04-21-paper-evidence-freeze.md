# Paper Evidence Freeze

| Row | Claims | Baseline | Dataset | Observed Status | Summary |
| --- | --- | --- | --- | --- | --- |
| c1_c2_building_google_full_system | C1, C2 | full_system | Gitega building OSM vs Google | passed | `docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json` |
| c5_building_msft_manual_baseline_contrast | C5 | manual_input_baseline | Gitega micro building OSM vs Microsoft, source-id materialized | passed | `docs/superpowers/specs/2026-04-16-building-micro-msft-fresh-checkout-result.json` |
| c3_replan_fault_recovery | C3 | no_repair_or_replan | fault-injected task-driven water/building/road runtime | passed | verification evidence |
| c4_learning_hints_pattern_selection | C4 | no_durable_learning_hints | durable summary seeded policy-hint contrast | passed | verification evidence |
| c1_c2_c7_scenario_trigger_autonomy | C1, C2, C7 | full_system | local file-inbox triggered disaster scenario | passed | scenario_trigger_proof evidence |
| c8_no_ui_operator_surface | C8-boundary | operator_api_smoke | persisted run and scenario evidence | passed | verification evidence |
| failure_micro_alignment_drift | C2-boundary | historical_failure | Gitega micro building OSM vs Google | failed | `docs/superpowers/specs/2026-04-08-building-micro-benchmark-result.json` |

## Frozen Rows

### `c1_c2_building_google_full_system`

- Claims: C1, C2
- Baseline: full_system
- Dataset: Gitega building OSM vs Google
- Observed status: passed
- Metrics: planning_validity_rate=pass, execution_success_rate=pass, artifact_validity=pass, evidence_completeness_rate=pass
- Raw artifacts: run_json=`runs/0b4315edf3a8449d940355717ad70fa7/run.json`, plan_json=`runs/0b4315edf3a8449d940355717ad70fa7/plan.json`, validation_json=`runs/0b4315edf3a8449d940355717ad70fa7/validation.json`, audit_jsonl=`runs/0b4315edf3a8449d940355717ad70fa7/audit.jsonl`, artifact_bundle=`runs/0b4315edf3a8449d940355717ad70fa7`

### `c5_building_msft_manual_baseline_contrast`

- Claims: C5
- Baseline: manual_input_baseline
- Dataset: Gitega micro building OSM vs Microsoft, source-id materialized
- Observed status: passed
- Metrics: execution_success_rate=pass, artifact_validity=pass, evidence_completeness_rate=pass, reproducibility_status=tracked_source_ids
- Raw artifacts: run_json=`runs/60e7afca80e146cd819fe87966d47e8c/run.json`, plan_json=`runs/60e7afca80e146cd819fe87966d47e8c/plan.json`, validation_json=`runs/60e7afca80e146cd819fe87966d47e8c/validation.json`, audit_jsonl=`runs/60e7afca80e146cd819fe87966d47e8c/audit.jsonl`, artifact_bundle=`runs/60e7afca80e146cd819fe87966d47e8c`

### `c3_replan_fault_recovery`

- Claims: C3
- Baseline: no_repair_or_replan
- Dataset: fault-injected task-driven water/building/road runtime
- Observed status: passed
- Summary: Focused Phase C regression proves source-changing replans refresh task-driven inputs and preserve plan revision evidence.
- Metrics: recovery_success_rate=pass, decision_trace_completeness=pass, execution_success_rate=pass
- Verification command: `python -m pytest -q tests/test_agent_run_service_enhancements.py::test_agent_run_service_replans_after_execution_failure tests/test_agent_run_service_enhancements.py::test_task_driven_replan_refreshes_inputs_when_source_changes`
- Verification result: 2 passed
- Evidence paths: `docs/superpowers/plans/done/2026-04-20-full-replan-loop-v1.md`, `tests/test_agent_run_service_enhancements.py`, `docs/superpowers/specs/2026-04-20-evaluation-contract-claim-lock.md`

### `c4_learning_hints_pattern_selection`

- Claims: C4
- Baseline: no_durable_learning_hints
- Dataset: durable summary seeded policy-hint contrast
- Observed status: passed
- Summary: Focused Phase D regression proves durable learning summaries emit bounded learning hints that influence pattern selection through an auditable score adjustment.
- Metrics: decision_trace_completeness=pass, planning_validity_rate=pass
- Verification command: `python -m pytest -q tests/test_policy_engine.py::test_policy_engine_applies_learning_adjustment_and_emits_it_in_evidence tests/test_agent_run_service_enhancements.py::test_pattern_selection_uses_durable_learning_summaries_as_policy_hints`
- Verification result: 2 passed
- Evidence paths: `docs/superpowers/plans/done/2026-04-20-durable-learning-policy-hints.md`, `tests/test_policy_engine.py`, `tests/test_agent_run_service_enhancements.py`, `docs/superpowers/specs/2026-04-20-evaluation-contract-claim-lock.md`

### `c1_c2_c7_scenario_trigger_autonomy`

- Claims: C1, C2, C7
- Baseline: full_system
- Dataset: local file-inbox triggered disaster scenario
- Observed status: passed
- Summary: Local trigger event normalizes into a scenario run, persists registry evidence, and freezes scenario reports without manual API submission.
- Metrics: planning_validity_rate=pass, evidence_completeness_rate=pass, decision_trace_completeness=pass
- Verification command: `python -m pytest -q tests/test_scenario_trigger_service.py tests/test_scenario_registry_service.py tests/test_api_scenario_registry.py`
- Verification result: 13 passed
- Evidence paths: `docs/superpowers/specs/2026-04-21-scenario-trigger-proof.md`, `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md`

### `c8_no_ui_operator_surface`

- Claims: C8-boundary
- Baseline: operator_api_smoke
- Dataset: persisted run and scenario evidence
- Observed status: passed
- Summary: No-UI operator APIs expose run listing, scenario listing, runtime summary, inspection, and comparison without requiring a frontend.
- Metrics: evidence_completeness_rate=pass, artifact_validity=pass
- Verification command: `python -m pytest -q tests/test_api_operator_read_models.py tests/test_api_v2_integration.py tests/test_api_scenario_registry.py`
- Verification result: .................                                                        [100%]
17 passed in 4.72s

### `failure_micro_alignment_drift`

- Claims: C2-boundary
- Baseline: historical_failure
- Dataset: Gitega micro building OSM vs Google
- Observed status: failed
- Metrics: execution_success_rate=fail
- Raw artifacts: artifact_bundle=`api-only run 8319c5bba5f64dd1a88ace78debaace5`


## Failure Analysis

- `failure_micro_alignment_drift`: Historical worker/runtime alignment drift, superseded by the clean 2026-04-16 rerun and kept only as a failure-case note.

## Qualitative Evidence

- `c7_water_uploaded_vertical_slice` (C7): Water shares the same task-driven runtime and evidence contract after Phase 1 stabilization. Keep the bounded extensibility note explicit even though the runtime contract is now shared. Paths: `docs/superpowers/plans/done/2026-04-20-water-vertical-slice.md`, `tests/test_water_adapter.py`, `docs/superpowers/specs/2026-04-20-evidence-ledger.md`
