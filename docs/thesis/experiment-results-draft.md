# Experiment Results Draft

This working draft is the bridge between frozen evidence and the future results chapter. It should not contain final numerical claims until the corresponding output is frozen through the evidence scripts.

## Current Evidence State

| Area | Current support | Result status |
| --- | --- | --- |
| KG-grounded executable planning | `c1_c2_building_google_full_system`, `c1_c2_c7_scenario_trigger_autonomy` | Frozen support for bounded planning and execution claims. |
| Bounded healing and replan | `c3_replan_fault_recovery` | Verification-frozen support for recovery behavior. |
| Evidence contract and inspection | `c1_c2_building_google_full_system`, `c8_no_ui_operator_surface` | Frozen support for evidence completeness and inspection surfaces. |
| Fusion quality benchmark | Freeze B protocol, readiness report, local blocker report, controlled supplement, and Caracas real-data supplement | Controlled semi-real supplement is frozen; Caracas real-data supplement is frozen as an independent real-world quality sanity benchmark; original real/Benin Freeze B cases remain blocked by missing artifacts and unavailable local source roots. |
| Freeze C ablations | `exp-ablation-a0-a2-controlled-comparison`, `exp-ablation-a0-a2-trace-backed-a2c` | Controlled A0/A1/A2a/A2b/A2c comparison frozen; A2c is inspection-derived with trace-backed provenance, and A0/A1/A2a/A2b are deterministic counterfactual rows. |
| Recovery governance | `exp-recovery-governance-c3` | C3 no-repair/no-replan contrast boundary, bounded healing/replan verified row, and fail-closed guard evidence are frozen as a thesis evidence table. |

## Runtime Governance

Freeze A establishes the runtime contract used by thesis experiments. The important result framing is that executable success must be separated from raw planning behavior. Report-only validation, fail-closed validation, KG fallback, and final executable success should appear as distinct columns in the final table.

Draft interpretation:

- A full-runtime pass supports the claim that KG-grounded planning can produce executable workflows inside the bounded task set.
- Validator rejection is not a failure by itself; it is evidence that unsupported or invalid plans are prevented from drifting into execution.
- KG fallback should be reported as a governance behavior, not hidden inside execution success.

## Ablation Results

The final ablation table must report:

- pre-fallback plan validity
- validator rejection rate
- KG fallback rate
- final executable success rate
- fallback or repaired plan quality delta when available

Current status: the controlled comparison is frozen as `docs/superpowers/specs/2026-06-10-freeze-c-ablation-a0-a2-manifest.json`. It uses four inspection-derived A2c rows and deterministic counterfactual rows for A0, A1, A2a, and A2b. The aggregation still does not run live API, LLM, or KG calls; it summarizes supplied rows under `controlled-ablation-counterfactual-v1`.

| Variant | Cases | Planning valid rate | Unknown algorithm rate | Execution success rate | Validator rejection rate | KG fallback rate | Average grounding score |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A0 | 4 | 0.25 | 0.75 | 0.25 | 0.0 | 0.0 | 0.0 |
| A1 | 4 | 0.75 | 0.0 | 0.75 | 0.0 | 0.0 | 0.375 |
| A2a | 4 | 0.75 | 0.0 | 1.0 | 0.0 | 0.0 | 0.5 |
| A2b | 4 | 0.75 | 0.0 | 1.0 | 0.25 | 0.25 | 0.5 |
| A2c | 4 | 0.75 | 0.0 | 1.0 | 0.25 | 0.0 | 0.5 |

This can now be used as a controlled ablation result for runtime-governance discussion. It should not be described as a fresh live LLM ablation run: the correct wording is that A0/A1/A2a/A2b are deterministic counterfactual rows derived from the frozen A2c inspection slice.

Trace-backed A2c provenance is now frozen separately as `docs/superpowers/specs/2026-06-24-freeze-c-ablation-a0-a2-trace-backed-manifest.json`. The provenance table reports `4/4` A2c inspection rows with required audit events and KG trace chains, `4/4` with declared artifacts, and `0/4` with artifact files present in the current workspace checkout. This supports inspection-level provenance, but not artifact-level re-evaluation unless the archived run outputs are restored.

## Recovery Results

The current recovery evidence supports a bounded statement: source-changing replans refresh task-driven inputs and preserve plan revision evidence under focused regression conditions. The results chapter should avoid claiming unconstrained self-healing or unlimited retry behavior.

Current frozen table:

| Condition | Role | Recovery allowed | Execution outcome | Promotion status |
| --- | --- | --- | --- | --- |
| `B0_no_repair_or_replan_boundary` | contrast boundary | No | Primary failure remains failed or requires manual intervention. | Boundary only, not an independent benchmark. |
| `B1_bounded_healing_replan_verified` | verified recovery row | Yes | Failed execution re-enters through healing, applies revision 2, refreshes inputs when source changes, and succeeds. | Frozen C3 evidence. |
| `G1_replan_grounding_fail_closed` | safety guard | Bounded | Ungrounded replanned workflow is rejected before execution. | Guard evidence. |
| `G2_replan_limit_fail_closed` | safety guard | Bounded by max plan revisions | Run fails with `replan_rejected` after the max revision limit. | Guard evidence. |

## Evidence Contract Results

Frozen paper rows currently support the claim that promoted runs expose plan, validation, run, audit, and artifact evidence. This should be reported as evidence completeness, not merely as a qualitative convenience.

Final table shape:

| Row | Evidence bundle | Inspection surface | Paper curation value |
| --- | --- | --- | --- |
| `c1_c2_building_google_full_system` | Present | Present | Main `C1/C2` evidence |
| `c8_no_ui_operator_surface` | Present | Present | Boundary evidence for no-UI inspection |

## Fusion Quality Results

Quality tables must report task-family metrics from machine-readable benchmark outputs. Completion-only success is not a substitute for fusion quality.

Required metric families:

- invalid geometry rate
- duplicate geometry rate
- source contribution balance
- task-specific checks where available

Current controlled supplement: `docs/superpowers/specs/2026-06-10-freeze-c-quality-controlled-supplement-manifest.json` freezes four deterministic semi-real cases. The benchmark summary reports that all four cases were accepted by their configured thresholds:

| Case | Task | Accepted | Threshold checks |
| --- | --- | --- | --- |
| `case.road.semi_real.perturbed` | road | True | invalid geometry rate = 0.0; zero-length count = 0 |
| `case.water_polygon.semi_real.priority_merge` | water polygon | True | invalid geometry rate = 0.0; sliver polygon count = 0 |
| `case.waterways.semi_real.line_conflation` | waterways | True | invalid geometry rate = 0.0; zero-length count = 0 |
| `case.poi.semi_real.neighbor_match` | POI | True | invalid geometry rate = 0.0; duplicate geometry rate = 0.0 |

This supplement can support a bounded statement that existing deterministic fusion adapters can produce structurally valid outputs on controlled semi-real fixtures. It cannot be used as a real Benin quality claim and does not replace the original Freeze B benchmark.

Current Caracas real-data supplement: `docs/superpowers/specs/2026-06-26-freeze-b-caracas-real-evidence-manifest.json` freezes a separate Caracas benchmark over five real cases. The benchmark summary reports 5/5 accepted quality-claim cases:

| Case | Task | Accepted | Boundary |
| --- | --- | --- | --- |
| `case.building.real.caracas` | building | True | overlap-priority fixed adapter; weak baseline, not external FusionCode V8 |
| `case.road.real.caracas` | road | True | FusionAgent road V7 conflation |
| `case.waterways.real.caracas` | waterways | True | FusionAgent waterways V7 conflation |
| `case.water_polygon.real.caracas.single_source_sanity` | water polygon | True | single-source OSM structural sanity only |
| `case.poi.real.caracas` | POI | True | GeoNames/OSM neighbor-match fusion |

The shared structural result is `invalid_geometry_rate = 0.0` for all five Caracas cases. The line cases also satisfy `zero_length_geometry_count = 0`; the building and POI cases satisfy their configured duplicate-geometry thresholds. This supports a bounded real-data statement that the current runtime/fusion adapters can produce structurally valid artifacts on a Caracas multi-domain dataset. It still does not establish superiority over external baselines or replace the original Benin Freeze B benchmark.

Original Freeze B status: keep real-world quality claims provisional until `exp-quality-freeze-b` output is frozen. The readiness report at `runs/experiments/exp-quality-freeze-b/readiness.json` shows five non-smoke Freeze B cases blocked by missing `precomputed_artifact_path` values; only the synthetic smoke case is currently non-blocking. The local blocker report at `runs/experiments/exp-quality-freeze-b/blocker_report.json` also records that `E:/fyx/data/Benin` and `D:/fyx/data/Benin` are unavailable in the current environment, so the real Benin benchmark cannot be completed from this checkout alone.

## Limitations

Fusion algorithms remain deterministic GIS implementations. The Caracas supplement improves the real-data quality evidence, but its building case is still a weak overlap-priority baseline and its water-polygon case is single-source sanity. The agentic contribution remains constrained planning, runtime governance, bounded repair and replan, auditability, and evidence lifecycle. The results chapter should keep this distinction visible so the thesis does not overclaim algorithmic novelty in the underlying GIS fusion routines.
