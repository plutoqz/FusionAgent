# FusionAgent No-UI Operations

## Purpose

This runbook consolidates the no-UI maturity operations path for FusionAgent before any final visualization frontend is introduced. It covers local runtime modes, scenario triggers, scenario regression, real-data evidence, evidence freezes, operator read APIs, artifact preview, cleanup, retention, and current boundaries.

Use this as the no-UI workflow entry point. Keep `docs/v2-operations.md` as the detailed runtime contract and troubleshooting reference rather than duplicating every operational detail here.

## Fast Runtime

Use fast mode for unit tests, API contract checks, planner/executor debugging, and scenario harness checks that do not require the full worker loop.

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
```

Terminal A:

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
uvicorn main:app --host 127.0.0.1 --port 8000
```

Terminal B:

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
python -m pytest -q `
  tests/test_eval_harness.py `
  tests/test_api_v2_integration.py `
  tests/test_agent_run_service_enhancements.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python scripts/eval_harness.py `
  --base-url http://127.0.0.1:8000 `
  --timeout 180 `
  --case building_disaster_flood `
  --case road_disaster_earthquake `
  --output-json tmp/eval/fast-confidence-summary.json
```

For a natural-language AOI smoke test:

```powershell
python scripts/smoke_agentic_region.py `
  --base-url http://127.0.0.1:8000 `
  --query "fuse building and road data for Nairobi, Kenya" `
  --timeout 1200
```

## Full-Loop Runtime

Use full-loop mode for worker, scheduler, Neo4j, Redis, and live-LLM integration checks.

```powershell
$env:GEOFUSION_KG_BACKEND='neo4j'
$env:GEOFUSION_LLM_PROVIDER='openai'
$env:GEOFUSION_CELERY_EAGER='0'
```

Start a local full-loop runtime with the repo-local dependency defaults:

```powershell
python scripts/start_local.py --port 8010
```

The default day-to-day API port remains `8000`; reserve `8010` for isolated real-data benchmark runs and `8011` for an isolated fast-confidence runtime when needed. See `docs/v2-operations.md` for Redis, Neo4j, worker, and port-alignment details.

## Scenario Trigger Inbox

The local file inbox is the supported no-UI trigger demo path. It proves normalized event records can create scenario runs, persist registry evidence, and move processed or failed event files without claiming an external event-feed integration. External event-feed replay is not supported in this phase.

Scenario runs stay bounded to `building`, `road`, `water`, and bounded `poi` orchestration. Requests that imply live event-feed replay, full digital twin outputs, unsupported layers, or unsupported dependency reasoning must be rejected or clarified before child runs start.

Current in-process entry point:

```python
process_inbox_once(inbox_dir, processed_dir, output_root=None, failed_dir=None)
```

Pass `failed_dir` when you want invalid JSON or runtime errors moved into an explicit failed-event directory; without it, the runner keeps fail-fast behavior and preserves the original event file.

CLI path:

```powershell
python scripts/watch_scenario_inbox.py `
  --inbox-dir tmp/scenario-inbox `
  --processed-dir tmp/scenario-processed `
  --failed-dir tmp/scenario-failed `
  --output-root E:\fyx\data\fusionagentTEST
```

Expected operator evidence:

- processed event JSON moves to `--processed-dir`
- invalid or failed event JSON moves to `--failed-dir` when provided
- scenario outputs are written under the request output root, `GEOFUSION_SCENARIO_OUTPUT_ROOT`, or `E:\fyx\data\fusionagentTEST`
- scenario registry records preserve idempotency and trigger metadata when present

## Scenario Regression Harness

Use the scenario harness for API-to-runtime scenario regression and paper/demo evidence.

```powershell
python scripts/scenario_eval_harness.py `
  --manifest docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json `
  --base-url http://127.0.0.1:8000 `
  --output-root E:\fyx\data\fusionagentTEST `
  --output-json tmp/eval/scenario-harness-summary.json `
  --timeout 1200
```

The current checked-in scenario set validates capability evidence as well as top-level phase. Building, road, and mixed cases require execution-level evidence; water and bounded POI may remain planner-level capability checks when local raw source materialization is unavailable in fast mode.

Use the real engineering validation runner when you need unattended scenario execution across the matrix:

```powershell
python scripts/run_engineering_validation.py `
  --matrix docs/superpowers/validation/engineering_validation_matrix.yaml `
  --base-url http://127.0.0.1:8010 `
  --output-root runs/engineering-validation/manual-20260604 `
  --timeout 1200
```

Expected validation outputs are `validation_session.json`, `matrix_snapshot.json`, `case_results.jsonl`, `validation_summary.json`, and `validation_summary.md`.

## Real-Data Benchmark

Use real-data benchmarks only when durable research evidence is needed.

Start the isolated runtime:

```powershell
python scripts/start_local.py --port 8010
```

For a clean-checkout benchmark path without restoring local `Data/`, prefetch bounded official assets first:

```powershell
python scripts/materialize_source_assets.py `
  --source raw.osm.building `
  --source raw.microsoft.building `
  --bbox 29.817351,-3.646572,29.931113,-3.412421 `
  --prefer-remote
```

Run the benchmark against the same isolated base URL:

```powershell
python scripts/eval_harness.py `
  --manifest docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json `
  --case building_gitega_micro_msft_agent `
  --base-url http://127.0.0.1:8010 `
  --timeout 1200 `
  --output-json tmp/eval/fresh-checkout-micro-msft.json
```

Record `base_url`, timeout, runtime metadata, `run_id`, and links to `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, and the artifact bundle.

## Evidence Freeze

Freeze paper evidence after curated benchmark or scenario evidence changes:

```powershell
python scripts/freeze_paper_evidence.py `
  --spec docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json `
  --output-json docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json `
  --output-markdown docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md
```

Freeze no-UI maturity evidence after the maturity target, gap ledger, paper evidence, and scenario evidence are current:

```powershell
python scripts/freeze_no_ui_maturity_evidence.py `
  --target docs/superpowers/specs/2026-04-21-no-ui-maturity-target.md `
  --gap-ledger docs/superpowers/specs/2026-04-21-no-ui-maturity-gap-ledger.md `
  --paper-evidence docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md `
  --scenario-evidence docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md `
  --output-json docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.json `
  --output-markdown docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.md
```

Do not track raw `runs/<run_id>/` directories or source caches as final evidence. Track frozen JSON/Markdown pointers instead.

## Evidence Lifecycle Contract

Single-run evidence is rooted at `runs/<run_id>/`. The source of truth is `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, `output/quality_report.json`, and the canonical artifact bundle.

Scenario evidence is rooted at `<scenario_output_root>/<scenario_id>/`. The source of truth is `scenario_summary.json`, `evaluation.json`, `kg_path_trace.json`, `workflow_trace.json`, `source_coverage.json`, `failed_children.json`, and `scenario_artifact_manifest.json`.

Validation evidence is rooted at the validation session output directory. The source of truth is `validation_session.json`, `matrix_snapshot.json`, `case_results.jsonl`, `validation_summary.json`, and `validation_summary.md`.

Raw source caches are disposable unless a frozen evidence file explicitly references them. Frozen JSON and Markdown records are the tracked evidence surface; raw run and cache directories stay untracked. In operational notes, write this plainly as: raw source caches are disposable.

## Operator APIs

The no-UI operator surface is read-oriented and intended for CLI/API inspection before any final frontend exists.

- `GET /api/v2/runs`: list persisted single-run records.
- `GET /api/v2/runs/{run_id}`: inspect raw run status.
- `GET /api/v2/runs/{run_id}/plan`: load persisted plan.
- `GET /api/v2/runs/{run_id}/audit`: load audit events.
- `GET /api/v2/runs/{run_id}/artifact`: download artifact bundle.
- `GET /api/v2/runs/{run_id}/inspection`: one-shot operational run view.
- `GET /api/v2/runs/{left_run_id}/compare/{right_run_id}`: compare two runs.
- `GET /api/v2/runtime`: capture non-sensitive runtime metadata.
- `GET /api/v2/operator/summary`: summarize runtime, worker-control, queue, run, scenario, evidence, and artifact state.
- `POST /api/v2/scenario-runs`: create a scenario-level run.
- `GET /api/v2/scenario-runs`: list scenario registry records.
- `GET /api/v2/scenario-runs/{scenario_id}`: inspect canonical scenario summary evidence.

`POST /api/v2/scenario-runs` is a bounded orchestration entry point. It is not a general simulation API, not a live event-feed replay path, and not a claim of full digital twin reasoning.

If an aggregate endpoint disagrees with raw `run.json`, `plan.json`, `audit.jsonl`, or scenario summary files, treat the raw evidence as source of truth and fix the API layer.

### Preflight And Recovery

- Use `POST /api/v2/runs/preflight` before creating operator-initiated runs when the request may contain unsupported scope.
- Use `GET /api/v2/operator/recovery` to inspect stale non-terminal runs and their checkpoint-derived recovery action.
- With worker beat enabled, `geofusion.recovery_tick` periodically acquires a per-run recovery lease and redispatches recoverable stale runs from the persisted request/checkpoint.
- Use `POST /api/v2/operator/recovery` for a manual recovery sweep or a single-run recovery request.

## Artifact Preview

Artifact previews are lightweight operator and future-UI assets generated from canonical artifact bundles. The current supported surfaces are the v2 API preview endpoints plus the underlying Python service utility.

API entry points:

- `GET /api/v2/runs/{run_id}/preview`: returns preview metadata for a succeeded run artifact.
- `GET /api/v2/runs/{run_id}/preview.geojson`: downloads the bounded GeoJSON preview generated from the canonical artifact bundle.

Service entry point:

Call the service utility from Python when you need the same bounded GeoJSON preview directly from an artifact ZIP:

```python
from pathlib import Path

from services.artifact_preview_service import build_artifact_preview

summary = build_artifact_preview(
    Path("runs/<run_id>/artifact.zip"),
    output_dir=Path("tmp/artifact-previews"),
    max_features=500,
)
```

Input is the canonical artifact ZIP produced by the v2 runtime. Output is a summary dict containing the GeoJSON preview path and metadata such as `feature_count`, `preview_feature_count`, `bbox`, `geometry_types`, and `crs`.

Failure and scope boundaries:

- artifacts without a declared CRS fail clearly because WGS84 preview generation would otherwise be ambiguous
- preview GeoJSON does not replace the canonical shapefile artifact bundle or frozen evidence records
- final dashboard rendering, map interaction, and frontend visualization remain out of scope
- preview generation is bounded to succeeded runs with a canonical artifact bundle; it is not a replacement for `run.json`, `plan.json`, `audit.jsonl`, or frozen evidence

## Cleanup And Retention

Keep checked-in evidence small and reproducible.

- Retain frozen JSON and Markdown evidence under `docs/superpowers/specs/`.
- Retain harness summaries in `tmp/eval/` only when they are intentionally referenced by a freeze or report.
- Do not commit raw `runs/`, `Data/`, downloaded source caches, or transient inbox directories.
- Move successful trigger events to the processed directory and invalid or failed events to the failed directory.
- Keep benchmark source caches under `runs/source-assets/` unless a separate evidence package explicitly records another location.

## Known Boundaries

- Final visual frontend is explicitly out of scope for this runbook.
- This is not a production SaaS, authentication, or multi-tenant deployment guide.
- The local trigger inbox is not an external event-feed provider integration.
- `trajectory-to-road` remains reservation-only and is not a live runtime ingestion path.
- In plain language: trajectory-to-road remains reservation-only and is not a live runtime ingestion path.
- Search space remains bounded to documented building, road, water, and bounded POI slices.
- Benin preparation and cleanup scripts may support research validation or data preparation, but they do not expand the stable runtime claim by themselves.
- Historical Google-backed building cases still depend on restored local `Data/` assets.
- AOI geocoding can depend on external availability and latency unless a deterministic local fixture/cache path is used.
