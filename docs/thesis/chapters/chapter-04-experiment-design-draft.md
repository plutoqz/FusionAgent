# Chapter 4 Draft: Experiment Design

## Experiment Goal

The experiments evaluate whether FusionAgent's bounded runtime mechanisms improve executable planning, failure recovery, and evidence inspectability. The design intentionally separates runtime success from fusion quality so the thesis does not treat a completed run as proof of high-quality geospatial conflation.

## Research Question Mapping

| RQ | Experiment slice | Primary evidence |
| --- | --- | --- |
| `RQ1` | KG-grounded planning and executable workflow validity | Paper evidence rows plus Freeze C ablation outputs. |
| `RQ2` | Bounded healing and replan under injected failures | `c3_replan_fault_recovery` plus no-healing comparison. |
| `RQ3` | Evidence contract completeness and inspection support | Paper evidence rows and operator/no-UI evidence surface checks. |

## Case Pool

The promoted case pool is limited to stable shared-runtime tasks:

- building
- road
- water
- bounded POI

Reserved or non-promoted cases are excluded from the main claim surface:

- trajectory-to-road
- final-product UI maturity
- unrestricted multi-source or raster-assisted building automation
- live external event-feed integration

## Metrics

| Metric family | Metrics | Interpretation |
| --- | --- | --- |
| Planning validity | `unknown_algorithm_rate`, `planning_valid_rate`, `validator_rejection_rate` | Whether the plan stays executable and contract-valid. |
| Runtime success | `execution_success_rate`, `final_executable_success_rate`, `kg_fallback_rate` | Whether the run reaches a valid executable outcome. |
| Recovery | `recovery_success_rate`, `policy_sourced_repair_count`, revision evidence completeness | Whether bounded failure handling improves outcomes without widening claims. |
| Evidence | `evidence_completeness_rate`, `decision_trace_completeness`, artifact availability | Whether outputs can be inspected and curated as paper evidence. |
| Fusion quality | invalid geometry rate, duplicate geometry rate, source contribution balance | Whether GIS outputs are structurally usable and task-specific quality checks pass. |

## Baselines And Ablations

| Baseline | Role | Current status |
| --- | --- | --- |
| A0 coarse task-to-handler runtime | Tests value of decomposed KG planning. | Frozen as controlled counterfactual rows. |
| A1 KG-aware but monolithic selection | Tests value of decomposition and grounding visibility. | Frozen as controlled counterfactual rows. |
| A2 full system | Main full-runtime comparison point. | Frozen for selected inspection-derived and controlled rows. |
| B0 no repair or replan | Tests value of healing and replan. | Verification frozen for current row. |
| C0 result-only output | Tests value of evidence contract. | Planned, not final-frozen. |

The current Freeze C ablation evidence has two layers. `exp-ablation-a0-a2-partial-inspection` preserves the original A2c/full-runtime slice derived from inspection payloads. `exp-ablation-a0-a2-controlled-comparison` adds deterministic counterfactual rows for A0, A1, A2a, and A2b and freezes the complete controlled comparison. This supports controlled ablation discussion, but it should not be described as a fresh live LLM/API/KG run.

The original Freeze B quality benchmark is also not ready for final real-world results. The readiness report shows that five non-smoke cases lack `precomputed_artifact_path`; those artifact paths must be materialized before real/Benin quality metrics can enter the results chapter.

A controlled semi-real supplement has been frozen as `exp-quality-freeze-b-controlled-supplement`. It contains four deterministic artifacts for road, water polygon, waterways, and POI cases, and all four are accepted by the configured quality thresholds. This supplement should be reported as controlled robustness evidence only, not as a replacement for original Freeze B real-world quality evaluation.

## Reporting Rule

The results chapter should use three labels:

- **Frozen result**: backed by current paper evidence freeze or a generated experiment manifest, with any partial or controlled-supplement scope label preserved.
- **Verification result**: backed by focused regression tests and explicitly scoped as such.
- **Pending experiment**: designed but not yet promoted to a numerical claim.

This avoids blending implementation confidence with final experimental evidence.
