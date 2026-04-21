# Paper Evidence Freeze

| Row | Claims | Baseline | Dataset | Observed Status | Summary |
| --- | --- | --- | --- | --- | --- |
| c1_c2_building_google_full_system | C1, C2 | full_system | Gitega building OSM vs Google | passed | `docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json` |
| c5_building_msft_manual_baseline_contrast | C5 | manual_input_baseline | Gitega micro building OSM vs Microsoft, source-id materialized | passed | `docs/superpowers/specs/2026-04-16-building-micro-msft-fresh-checkout-result.json` |
| failure_micro_alignment_drift | C2-boundary | historical_failure | Gitega micro building OSM vs Google | failed | `docs/superpowers/specs/2026-04-08-building-micro-benchmark-result.json` |

## Failure Analysis

- `failure_micro_alignment_drift`: Historical worker/runtime alignment drift, superseded by the clean 2026-04-16 rerun and kept only as a failure-case note.

## Qualitative Evidence

- `c7_water_uploaded_vertical_slice` (C7): Uploaded-only water slice proves bounded extensibility beyond building and road without claiming task-driven auto water acquisition.
