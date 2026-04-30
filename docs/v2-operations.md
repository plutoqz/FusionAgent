# FusionAgent v2 Operations

## Current Position

`v2` is the current agentic runtime line in this repo. It is not a full product surface yet, but it now has:

- explicit planning, validation, execution, healing, and writeback stages
- persisted `run.json`, `plan.json`, `validation.json`, and `audit.jsonl`
- durable learning summaries for long-term planning evidence
- operator-facing inspection and comparison endpoints in the v2 API
- an operator-facing web workbench for runs, scenarios, KG views, and LLM settings
- stable task-driven support for `building`, `road`, `water`, and bounded `poi` on the shared runtime backbone

For the consolidated no-UI maturity operating workflow, see [FusionAgent No-UI Operations](./no-ui-agent-operations.md).

## Stability Contract

Freeze the runtime wording to the following contract:

- `building: task_driven_auto supported`
- `road: task_driven_auto supported`
- `water: task_driven_auto supported after Phase 1`
- `poi: bounded task_driven_auto supported after Phase 3`
- all four share the same evidence contract: `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, and the artifact bundle
- `trajectory-to-road` remains reservation-only in Phase 4 and is not part of the stable runtime contract

### Benin Preparation Boundary

For the Benin building-runtime preparation slice, keep the capability wording frozen as:

| Capability | Status |
| --- | --- |
| tiled parallel execution for the current `OSM + single-ref` building runtime | supported |
| Benin canonical source profiling | supported |
| KG exposure for OpenBuildingMap / local Microsoft / Google Open Buildings | supported in KG, not executable |
| Google building-presence raster inspection and profiling | inspect-only |
| raster-based building presence validation and height extraction | executable via FusionCode decomposed primitives once raster artifacts are materialized |
| true multi-source building fusion semantics | executable via `wp.building.drs4br.decomposed.v1` and `algo.fusion.building.multi_source.decomposed.v1` |

FusionCode integration is deliberately decomposed in KG. The planner can surface the executable primitives for source normalization, presence-raster validation, V8 candidate graph generation, component solving, cascade geometry-priority fusion, conflict optimization, post-conflict refinements, height-raster enrichment, and quality metrics. Raster and extra vector catalog entries may still be marked `reservation_only` as data sources when local materialization is unavailable; that is distinct from the algorithm capability, which is now represented by executable runtime-candidate nodes.

Operator commands:

```powershell
python scripts/profile_benin_sources.py --source-root E:\fyx\data\Benin --output runs\benin-source-profile.json
python scripts/benchmark_tiled_building.py --source-root E:\fyx\data\Benin --bbox 2.48,9.23,2.77,9.44 --target-crs EPSG:32631 --output-root runs\benin-benchmark
```

For the Benin national multi-source building workflow, use the FusionCode tiled runtime instead of the legacy two-source benchmark:

```powershell
python scripts/run_benin_multisource_building_fusion.py `
  --source-root E:\fyx\data\Benin `
  --output-root runs\benin-national-multisource `
  --target-crs EPSG:32631 `
  --tile-width-m 10000 `
  --tile-height-m 10000 `
  --overlap-m 96 `
  --max-workers 4
```

This writes `runtime_output/fused_buildings.gpkg` and preserves `height_ms`, `height_obm`, `height_google`, `height_osm`, optional `height_raster`, plus `height_final` and `height_final_source`.

### Artifact Preview Products

The no-UI maturity path can generate lightweight GeoJSON previews from artifact bundles before any final dashboard exists. These previews are operator and future-UI assets; they do not replace the canonical shapefile artifact bundle.

### System-Next Improvement Boundary

The next system-improvement chain is controlled by:

- [System-Next Improvement Review](./superpowers/specs/2026-04-23-system-next-improvement-review.md), which maps each review challenge to required evidence before claims can be promoted.
- [Complexity Boundary Ledger](./superpowers/specs/2026-04-23-complexity-boundary-ledger.md), which separates core runtime proof from deferred or optional complexity.

The authorized next additions are registered tool contracts, KG grounding reports, unsupported-intent rejection, token/latency telemetry, checkpoint recovery inspection, and ablation evidence. In runtime terms, that means a `ToolSpec` registry, per-step grounding artifacts, unsupported-request guards, run telemetry, and checkpoint or stale-run recovery scanning. These additions strengthen the current no-UI operating layer; they do not authorize production `7x24` operation wording, arbitrary off-domain request claims, final UI completion claims, external event-feed integration claims, live trajectory-to-road ingestion claims, or autonomous durable learning claims beyond bounded policy hints.

## Runtime Modes

### Local Fast Mode

Use this for unit tests, API contract checks, and planner or executor debugging.

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
```

### Local Full-Loop Mode

Use this for worker, scheduler, Neo4j, and live-LLM integration checks.

```powershell
$env:GEOFUSION_KG_BACKEND='neo4j'
$env:GEOFUSION_LLM_PROVIDER='openai'
$env:GEOFUSION_CELERY_EAGER='0'
```

## Standard Local Conventions

- default day-to-day API port: `8000`
- default frontend dev port: `5173`
- standard full-loop startup command: `python scripts/start_local.py --port 8000`
- `main.py`, `worker/celery_app.py`, and `scripts/start_local.py` auto-load repo-local dependency defaults, so local broker / backend settings follow `依赖.txt` before falling back to the generic code default
- the current repo-local example uses Redis on `localhost:6380`; the generic code fallback remains `redis://localhost:6379/0`
- default Neo4j convention: `bolt://localhost:7687`
- reserve `8011` for an isolated fast-confidence runtime when you do not want to share the default `8000` app
- reserve `8010` for isolated real-data benchmark runs so the benchmark base URL, worker logs, and evidence directory can stay aligned
- use `8012+` only for temporary diagnostics or one-off worktree isolation
- official benchmark source-asset downloads are cached under `runs/source-assets/`; local `Data/` is still preferred unless you explicitly force remote materialization
- task-driven AOI runs now resolve a natural-language location before planning and can fall back to official Geofabrik / Microsoft downloads when local `Data/` is incomplete
- scenario-level runs accept an explicit output root. If omitted, `GEOFUSION_SCENARIO_OUTPUT_ROOT` is used. If that is also unset, scenario outputs are written under `E:\fyx\data\fusionagentTEST`.
- the frontend defaults to Simplified Chinese, and users can switch to English from the sidebar
- FastAPI allows `http://127.0.0.1:5173` and `http://localhost:5173` for local frontend development by default; override with `GEOFUSION_CORS_ORIGINS` when needed
- when `frontend/dist/` exists, FastAPI serves it on `/` and falls back to `index.html` for non-`/api/*` SPA routes
- `docker compose` is a separate path: it uses container-local `redis://redis:6379/0` and API port `8000`, not the host-side `依赖.txt` mapping

## Evaluation Tiers

### Tier 1: Targeted Tests

Use this for everyday development and regression control.

Minimum evidence:

- exact `pytest` command
- pass or fail output
- failing test names when red
- for AOI work, the resolved place name and selected source id when available

Focused system-next regression command:

```powershell
python -m pytest -q tests/test_tool_registry.py tests/test_plan_grounding_service.py tests/test_unsupported_intent_guard.py tests/test_run_telemetry_service.py tests/test_run_recovery_service.py tests/test_eval_kg_ablation.py
```

### Tier 2: Golden-Case Harness

Use this when you need an API-to-runtime closed loop without paying the cost of a real-data benchmark.

Minimum evidence:

- saved harness summary JSON
- failed `case_id`
- related `run_id` when available

Scenario-level paper/demo harness:

```powershell
python scripts/scenario_eval_harness.py `
  --manifest docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json `
  --base-url http://127.0.0.1:8000 `
  --output-root E:\fyx\data\fusionagentTEST `
  --output-json tmp/eval/scenario-harness-summary.json `
  --timeout 1200
```

The checked-in scenario regression set now validates capability evidence in addition to the top-level phase. Building, road, and mixed execution cases require execution-level evidence such as `task_inputs_resolved`, `source_coverage`, and a minimum successful child-run count; water and bounded POI cases currently use planner-level capability checks such as `aoi_resolved`, `kg_path_selected`, and `plan_validated` when local raw source materialization is not yet stable in the default fast-mode environment.

Task 5 live scenario harness deferral record:

- Date: 2026-04-21
- Command:

```powershell
python scripts/scenario_eval_harness.py `
  --manifest docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json `
  --base-url http://127.0.0.1:8000 `
  --output-root E:\fyx\data\fusionagentTEST `
  --output-json tmp/eval/scenario-harness-summary.json `
  --timeout 1200
```

- Deferred reason: `http://127.0.0.1:8000/api/v2/runtime` returned connection refused; local API was unavailable.
- This deferral is not counted as a passing live scenario harness result.
- Water and bounded POI scenario capability checks were not upgraded to execution-level claims.

### Tier 3: Real-Data Benchmark

Use this only when you need durable research evidence.

Minimum evidence:

- saved benchmark summary JSON
- `run_id`
- matching `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, and artifact bundle
- `base_url`, timeout, and key environment notes
- when available, rely on `/api/v2/runtime` so harness summaries capture actual runtime metadata rather than only the shell that launched the harness

### Phase G Evidence Freeze

After benchmark reruns are curated, freeze the tracked paper evidence with:

```powershell
python scripts/freeze_paper_evidence.py `
  --spec docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json `
  --output-json docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json `
  --output-markdown docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md
```

Track the matrix spec and frozen outputs under `docs/superpowers/specs/`.
Do not track raw `runs/<run_id>/` directories or source caches; record their storage location inside the frozen JSON instead.
Keep the water and bounded POI extensibility notes explicit even though both now share the stable task-driven contract.
Do not describe the trajectory-to-road seam reservation as a live runtime ingestion path.

## Timeout Guidance

- `scripts/eval_harness.py` still defaults to `180` seconds
- that default is acceptable for fast confidence checks, not for real building benchmarks
- current real-data building runs should use an explicit timeout such as `1200`
- when a benchmark times out, verify timeout policy and runtime alignment before blaming the algorithm

## Recommended Commands

### Frontend Workbench

Terminal A:

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
uvicorn main:app --host 127.0.0.1 --port 8000
```

Terminal B:

```powershell
Set-Location frontend
npm install
npm run dev
```

For same-origin serving:

```powershell
Set-Location frontend
npm run build
Set-Location ..
uvicorn main:app --host 127.0.0.1 --port 8000
```

### Fast Confidence

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

If you intentionally need a second isolated fast-confidence runtime while `8000` is busy, reuse the same command pattern on `8011` and keep the `base_url` aligned.

Natural-language AOI smoke:

- when `task_driven_auto` resolves an AOI and the caller omits `target_crs`, the runtime derives a projected UTM CRS from the AOI bbox centroid
- explicit `target_crs` still wins; pass `target_crs=EPSG:4326` only when you intentionally want geographic output

```powershell
python scripts/smoke_agentic_region.py `
  --base-url http://127.0.0.1:8000 `
  --query "fuse building and road data for Nairobi, Kenya" `
  --timeout 1200
```

### Real Evidence

Start a fresh isolated full-loop runtime first:

```powershell
python scripts/start_local.py --port 8010
```

If you want a clean-checkout benchmark path without restoring local `Data/`, prefetch the bounded official assets first:

```powershell
python scripts/materialize_source_assets.py `
  --source raw.osm.building `
  --source raw.microsoft.building `
  --bbox 29.817351,-3.646572,29.931113,-3.412421 `
  --prefer-remote
```

Then run the benchmark against the same isolated base URL:

```powershell
python scripts/eval_harness.py `
  --manifest docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json `
  --case building_gitega_micro_msft_agent `
  --base-url http://127.0.0.1:8010 `
  --timeout 1200 `
  --output-json tmp/eval/fresh-checkout-micro-msft.json
```

This bounded fresh-checkout path is tracked in `docs/superpowers/specs/2026-04-16-building-micro-msft-fresh-checkout-result.json`.
Historical Google-backed building cases are still useful, but they continue to depend on restored local `Data/` assets rather than the new official-download cache.

## Fresh-Checkout Source Asset Materialization

The repo now has one bounded official-source materialization path for benchmark reproduction.

- manifest cases may use `inputs.osm_source_id` and `inputs.reference_source_id` in addition to direct local shapefile paths
- `scripts/eval_harness.py` resolves those source ids through `services/source_asset_service.py`
- `scripts/materialize_source_assets.py` can prefetch the same assets into `runs/source-assets/`
- local `Data/` files are still preferred when they are complete; incomplete local shapefile bundles are skipped and replaced by cache-backed official assets

Currently materializable source ids:

- `raw.osm.building`
- `raw.osm.road`
- `raw.osm.water`
- `raw.osm.poi`
- `raw.microsoft.building`

| Source ID | Local Data Supported | Remote Materialization Supported | Current Claim |
| --- | --- | --- | --- |
| raw.osm.building | yes | yes | mature no-UI supported |
| raw.osm.road | yes | yes | mature no-UI supported |
| raw.osm.water | yes | yes | planner-level scenario evidence unless execution source is available |
| raw.osm.poi | yes | yes | bounded POI evidence only |
| raw.microsoft.building | yes | yes | mature no-UI supported for bounded building |
| raw.google.building | yes | no | manual/local-only boundary |

Water and bounded POI are mature as bounded task-driven runtime slices, but the default fast-mode scenario regression set still treats them as planner-level capability checks when local raw source materialization is unavailable.

Current non-goals for this slice:

- `raw.google.building` still requires locally restored data
- local-only reference or Excel-style inputs are still manual
- AOI resolution still depends on external geocoding availability and request latency

## Operator Inspection API

The v2 API now has a narrow but practical operator layer.

### Scenario Runs

- `POST /api/v2/scenario-runs`: starts a scenario-level orchestration request above one or more v2 child runs
- `GET /api/v2/scenario-runs`: lists persisted scenario registry records from `scenario_runs_index.jsonl`
- `GET /api/v2/scenario-runs/{scenario_id}`: loads the canonical `scenario_summary.json` for a scenario
- request fields include `scenario_name`, `trigger_content`, `disaster_type`, `job_types`, optional `target_crs`, and optional `output_root`
- output-root order is `request.output_root`, then `GEOFUSION_SCENARIO_OUTPUT_ROOT`, then `E:\fyx\data\fusionagentTEST`
- scenario output includes `scenario_summary.json`, `kg_path_trace.json`, `workflow_trace.json`, `source_coverage.json`, `evaluation.json`, and bilingual reports under `documents/scenario_report.zh.md` and `documents/scenario_report.en.md`
- scenario evidence is additive; single-run `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, and artifact bundles remain stable
- scenario reports expose KG relationship chains, final workflow trace, source coverage and fallback evidence, data-fusion metrics, agentic metrics, and durable learning summary or policy-hint evidence

The file inbox runner is an operations demo path, not a production event-feed integration. It proves that scenario requests can be triggered automatically from normalized event records while keeping external feed reliability out of this phase.

### Single Run Inspection

- `GET /api/v2/runs/{run_id}`: raw run status
- `GET /api/v2/runs/{run_id}/plan`: persisted plan
- `GET /api/v2/runs/{run_id}/audit`: full audit event stream
- `GET /api/v2/runs/{run_id}/artifact`: artifact bundle download
- `GET /api/v2/runs/{run_id}/inspection`: one-shot operational view of status, plan, audit events, KG path trace, and artifact metadata
- `GET /api/v2/runtime`: non-sensitive runtime metadata for evidence capture and alignment checks (`kg_backend`, `llm_provider`, `celery_eager`, `api_port`)

### Run Comparison

- `GET /api/v2/runs/{left_run_id}/compare/{right_run_id}`: side-by-side run comparison using the same inspection payload
- the compare endpoint keeps raw evidence visible; it does not replace the underlying `/plan`, `/audit`, or `/artifact` endpoints

## Runtime Alignment Checklist

Before running Tier 2 or Tier 3 checks, verify:

### 1. API Port Alignment

- the `base_url` matches the runtime you actually started
- you are not accidentally talking to an older worker or older app port

### 2. Worker Freshness

- current worker logs show a fresh startup timestamp
- queued runs are actually being consumed

### 3. Output Directory Alignment

- benchmark evidence is being written under the current runtime's `runs/` directory
- saved summaries reference the same `run_id` tree you inspected

### 4. Input and Dependency Alignment

- manifest inputs exist
- dependency files point to the intended versions
- you are not mixing worktrees or stale temp directories

### 5. Evidence Alignment

- Tier 2 keeps harness summary and failed `case_id`
- Tier 3 can be traced back to `run.json`, `plan.json`, `audit.jsonl`, and artifact bundle

## Neo4j

Bootstrap:

```bash
python -m kg.bootstrap
```

Useful commands:

```bash
python -m kg.bootstrap --prepare-local --json
python -m kg.bootstrap --prepare-local --reset-managed --json
python -m kg.bootstrap --inspect --json
python -m kg.bootstrap --inspect --managed-only --json
```

## Celery / Redis

Local direct-run note:

- the preferred path is `python scripts/start_local.py --port 8000`
- when you start `uvicorn` or `celery` manually, the entrypoints still auto-load repo-local defaults from `依赖.txt`
- if you bypass that mechanism, make sure `GEOFUSION_CELERY_BROKER` and `GEOFUSION_CELERY_BACKEND` match the intended host Redis port before blaming queued runs on the worker

Worker:

```bash
celery -A worker.celery_app.celery_app worker -l info
```

Beat:

```bash
celery -A worker.celery_app.celery_app beat -l info
```

## Scheduled Runs

`GEOFUSION_SCHEDULED_RUNS` remains a JSON array, for example:

```json
[
  {
    "job_type": "road",
    "trigger_content": "hourly road refresh",
    "disaster_type": "earthquake",
    "osm_zip_path": "E:/data/road/osm.zip",
    "ref_zip_path": "E:/data/road/ref.zip",
    "target_crs": "EPSG:32643"
  }
]
```

## Troubleshooting

### Run Stuck In `planning` Or `validating`

Inspect:

- `runs/<run_id>/run.json`
- `runs/<run_id>/plan.json`
- `runs/<run_id>/validation.json`
- `runs/<run_id>/audit.jsonl`

### Artifact Missing

Check:

- the input ZIP contains `.shp`, `.shx`, and `.dbf`
- the output directory contains the produced shapefile bundle
- repair strategies were not exhausted

### Compare Or Inspection Looks Wrong

Treat the raw evidence as the source of truth:

- `run.json`
- `plan.json`
- `audit.jsonl`
- artifact bundle

If the aggregated API view disagrees with those files, fix the API layer rather than rewriting the evidence.
