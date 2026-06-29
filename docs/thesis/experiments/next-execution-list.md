# Next Execution List

This list is the concrete next-step queue for research and thesis work. It keeps executable experiment work separate from writing work.

## Batch 1: Stabilize Thesis Evidence Workspace

| Item | Action | Output | Done when |
| --- | --- | --- | --- |
| 1.1 | Refresh paper evidence freeze with the canonical matrix. | `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.{json,md}` | Generated files match script output and tests pass. |
| 1.2 | Render Freeze C thesis table from current generated manifests. | `docs/superpowers/specs/2026-06-10-thesis-evidence-tables.md` | Table includes the controlled ablation manifest, partial provenance manifest, and controlled quality supplement manifest with correct scope labels. |
| 1.3 | Keep all new thesis-facing files under `docs/thesis`. | `docs/thesis/README.md`, `chapters/`, `experiments/`, `evidence/` | New thesis drafts have a single entry point. |

## Batch 2: Automatic Fusion Evidence

| Item | Action | Output | Promotion target |
| --- | --- | --- | --- |
| 2.1 | Select one current building full-system evidence row as the main example. | Row note in results chapter | `C1/C2` |
| 2.2 | Select road, water, and bounded POI smoke evidence as supporting examples. | Supporting table or appendix note | `C7` only |
| 2.3 | Verify each promoted run has `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, and artifact bundle. | Evidence completeness table | `C2` |

## Batch 3: KG Ablation Inputs

`scripts/eval_kg_ablation.py` aggregates supplied rows. It does not generate live LLM, KG, or API runs by itself. The controlled input JSON now contains rows for supported variants:

- `A0`
- `A1`
- `A2a`
- `A2b`
- `A2c`

Current progress: `runs/experiments/exp-ablation-a0-a2` now contains both the original inspection-derived partial A2c slice and the full controlled comparison generated from it. `docs/superpowers/specs/2026-06-10-freeze-c-ablation-a0-a2-manifest.json` freezes the controlled comparison. `docs/superpowers/specs/2026-06-24-freeze-c-ablation-a0-a2-trace-backed-manifest.json` separately freezes the A2c trace-backed provenance table. Use the full manifest for Chapter 5 ablation tables, and cite the trace-backed manifest when discussing A2c inspection provenance.

Each row must include:

- `variant`
- `planning_valid`
- `unknown_algorithms`
- `execution_success`
- `grounding_score`
- optional `validator_rejected`
- optional `kg_fallback_used`
- optional `llm_plan_valid_before_fallback`
- optional `fallback_plan_quality_delta`

Rebuild command:

```powershell
python scripts/materialize_controlled_ablation_rows.py `
  --input-json runs/experiments/exp-ablation-a0-a2/input_rows.json `
  --output-json runs/experiments/exp-ablation-a0-a2/input_rows_controlled.json `
  --output-markdown runs/experiments/exp-ablation-a0-a2/input_rows_controlled.md

python scripts/eval_kg_ablation.py `
  --input-json runs/experiments/exp-ablation-a0-a2/input_rows_controlled.json `
  --output-json runs/experiments/exp-ablation-a0-a2/ablation_summary_controlled.json `
  --output-markdown runs/experiments/exp-ablation-a0-a2/ablation_summary_controlled.md
```

Then freeze the output:

```powershell
python scripts/freeze_experiment_evidence.py `
  --experiment-id exp-ablation-a0-a2-controlled-comparison `
  --output-dir runs/experiments/exp-ablation-a0-a2 `
  --output-json docs/superpowers/specs/2026-06-10-freeze-c-ablation-a0-a2-manifest.json `
  --seed-hash inspection-smoke-2026-05-12-plus-controlled-counterfactual-v1 `
  --runtime-settings-hash controlled-ablation-counterfactual-v1 `
  --metric-definition-hash eval-kg-ablation-v1
```

Trace-backed A2c provenance command:

```powershell
python scripts/export_trace_backed_ablation_evidence.py `
  --input runs\smoke-building-gitega-city-inspection-8012.json `
  --input runs\smoke-road-gilgit-city-inspection-8012.json `
  --input runs\smoke-water-nairobi-inspection-8012.json `
  --input runs\smoke-poi-nairobi-inspection-8012.json `
  --output-json runs\experiments\exp-ablation-a0-a2-trace-backed\trace_backed_a2c_evidence.json `
  --output-markdown runs\experiments\exp-ablation-a0-a2-trace-backed\trace_backed_a2c_evidence.md

python scripts/freeze_experiment_evidence.py `
  --experiment-id exp-ablation-a0-a2-trace-backed-a2c `
  --output-dir runs\experiments\exp-ablation-a0-a2-trace-backed `
  --output-json docs\superpowers\specs\2026-06-24-freeze-c-ablation-a0-a2-trace-backed-manifest.json `
  --seed-hash inspection-smoke-2026-05-12 `
  --runtime-settings-hash trace-backed-a2c-evidence-v1 `
  --metric-definition-hash trace-backed-ablation-evidence-v1
```

## Batch 4: Fusion Quality Benchmark

`scripts/run_fusion_quality_benchmark.py` expects benchmark cases with precomputed artifact paths. The next task is to identify or produce stable artifact paths for the Freeze B manifest before running the benchmark.

Completed supplement:

```text
docs/superpowers/specs/2026-06-10-freeze-b-controlled-supplement-manifest.json
runs/experiments/exp-quality-freeze-b-controlled
docs/superpowers/specs/2026-06-10-freeze-c-quality-controlled-supplement-manifest.json
docs/superpowers/specs/2026-06-26-freeze-b-caracas-real-manifest.json
runs/experiments/exp-quality-freeze-b-caracas-real
docs/superpowers/specs/2026-06-26-freeze-b-caracas-real-evidence-manifest.json
```

This controlled semi-real supplement can be cited as bounded robustness evidence only. It does not replace the original Freeze B real/Benin case set.

The Caracas real-data supplement can be cited as independent real-data structural-quality evidence. It includes five quality-claim cases over building, road, waterways, water polygon, and POI data; all five are accepted by their configured structural thresholds. It is still bounded: the building case uses an overlap-priority weak baseline rather than external FusionCode V8, the water-polygon case is single-source structural sanity, and the supplement does not replace the original Benin Freeze B benchmark.

Current readiness report:

```text
runs/experiments/exp-quality-freeze-b/readiness.json
runs/experiments/exp-quality-freeze-b/readiness.md
```

The report currently blocks five non-smoke cases because `precomputed_artifact_path` is missing in `docs/superpowers/specs/2026-06-10-freeze-b-benchmark-manifest.json`. The local blocker report additionally records that `E:\fyx\data\Benin` and `D:\fyx\data\Benin` are unavailable in the current environment.

Blocker report command:

```powershell
python scripts/export_freeze_b_blocker_report.py `
  --manifest docs\superpowers\specs\2026-06-10-freeze-b-benchmark-manifest.json `
  --output-json runs\experiments\exp-quality-freeze-b\blocker_report.json `
  --output-markdown runs\experiments\exp-quality-freeze-b\blocker_report.md

python scripts/freeze_experiment_evidence.py `
  --experiment-id exp-quality-freeze-b-local-blocker-report `
  --output-dir runs\experiments\exp-quality-freeze-b `
  --output-json docs\superpowers\specs\2026-06-24-freeze-b-local-blocker-manifest.json `
  --seed-hash freeze-b-v1 `
  --runtime-settings-hash local-source-root-check-v1 `
  --metric-definition-hash freeze-b-readiness-blocker-v1
```

Original Benin target output directory:

```text
runs/experiments/exp-quality-freeze-b
```

Original Benin target freeze manifest:

```text
docs/superpowers/specs/2026-06-10-freeze-c-quality-freeze-b-manifest.json
```

Promotion rule: quality metrics can enter Chapter 5 only after the manifest is generated and the benchmark summary is referenced from `docs/thesis/evidence/evidence-index.md`. Caracas now satisfies this rule as a separate real-data supplement; original Benin remains blocked until its source assets and precomputed artifacts are available.

## Batch 4.5: Recovery Governance Evidence

Current progress: `docs/superpowers/specs/2026-06-24-freeze-c-recovery-governance-manifest.json` freezes the C3 recovery governance table. It summarizes a no-repair/no-replan contrast boundary, the bounded healing/replan verified row, and fail-closed guard rows for grounding rejection and max revision limits. This is a thesis evidence table, not a statistical benchmark.

Rebuild command:

```powershell
python scripts/export_recovery_governance_evidence.py `
  --paper-freeze docs\superpowers\specs\2026-04-21-paper-evidence-freeze.json `
  --output-json runs\experiments\exp-recovery-governance\recovery_governance_evidence.json `
  --output-markdown runs\experiments\exp-recovery-governance\recovery_governance_evidence.md

python scripts/freeze_experiment_evidence.py `
  --experiment-id exp-recovery-governance-c3 `
  --output-dir runs\experiments\exp-recovery-governance `
  --output-json docs\superpowers\specs\2026-06-24-freeze-c-recovery-governance-manifest.json `
  --seed-hash paper-evidence-freeze-2026-04-21 `
  --runtime-settings-hash recovery-governance-table-v1 `
  --metric-definition-hash c3-recovery-governance-v1
```

## Batch 5: Writing

| Chapter | Immediate action | Evidence dependency |
| --- | --- | --- |
| Chapter 1 | Expand research background and contribution paragraphs. | Current thesis spec and claims ledger are enough. |
| Chapter 2 | Refresh related-work discussion and gap framing. | Related-work matrix plus literature refresh. |
| Chapter 3 | Add method diagram and service-level references. | Current runtime contract and KG gate docs are enough. |
| Chapter 4 | Convert experiment design draft into formal protocol. | Current matrix plus next ablation plan. |
| Chapter 5 | Use frozen controlled ablation, controlled quality supplement, and Caracas real-data supplement with labels; keep superiority claims provisional. | Original Freeze B artifacts, external/weak baselines, and larger live ablations are still needed for stronger real-world claims. |

## Stop Conditions

- Stop adding capabilities if the work does not produce evidence for `C1`, `C2`, or `C3`.
- Stop promoting new result claims if the evidence is only a smoke run or sample manifest.
- Stop scattering new thesis drafts outside `docs/thesis` unless a script or existing test requires the older location.
