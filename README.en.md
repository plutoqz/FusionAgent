# FusionAgent

[中文说明](./README.md)

Resume/demo project brief: [FusionAgent Resume Project Brief](./docs/demo/fusionagent-resume-project-brief.md).

FusionAgent is a mature vector-data fusion agent runtime for bounded disaster
response workflows, and the current codebase now includes an operator-facing
web workbench foundation. The code is no longer just a script wrapper. It now
provides a testable, auditable, and incrementally extensible KG-grounded,
contract-bounded agentic workflow runtime.

The runtime now stably supports `building`, `road`, and `water`, and also adds
a bounded `poi` automatic-fusion slice on the same task-driven runtime
backbone. All four participate in the same planning, validation, execution,
healing, replanning, evidence writeback, and artifact output contract.

## Current Position

The most accurate description of the project today is:

- Engineering MVP: reached
- Research prototype: reached
- Mature no-UI vector data fusion agent: reached
- Final visualization product shape: not reached

FusionAgent has now reached the engineering MVP, research prototype, and mature
no-UI vector data fusion agent bar, but it should still not be described as the
final visualization product or as an unbounded general-purpose agent.

FusionAgent can now operate as a mature vector data fusion agent within its
bounded scope: it provides natural-language and local scenario-trigger entry
points, KG-constrained planning, task-driven data acquisition,
execution/healing/replanning/learning evidence, scenario-level evidence
freeze, operator read APIs, a local operations runbook, and an operator-facing
v2 web workbench foundation. The final product-grade visualization UI remains
future work.

The next engineering increment stays narrowly scoped to operating and evidence
improvements: registered tool contracts, KG grounding reports,
unsupported-intent rejection, token/latency telemetry, checkpoint recovery
inspection, and ablation evidence.

## Web Workbench

The repo now ships an operator-facing frontend foundation with:

- home overview, run creation, run list, run detail, and run comparison pages
- scenario report browsing, GeoJSON map previews, KG overview, and run path graph pages
- LLM settings read, validation, and persistence flows
- Simplified Chinese as the default locale, with an `English` toggle in the sidebar and persisted browser preference

This frontend is intended to close the operator control-plane gap. It should
not be described as the final product UI.

## Stability Contract

The public runtime contract is now frozen as:

- `building: task_driven_auto supported`
- `road: task_driven_auto supported`
- `water: task_driven_auto supported after Phase 1`
- `poi: bounded task_driven_auto supported after Phase 3`
- all four share the same evidence contract: `run.json`, `plan.json`, `validation.json`, `audit.jsonl`, and the artifact bundle

## Benin Building Runtime Preparation

The current Benin large-building-runtime preparation boundary is:

| Capability | Status |
| --- | --- |
| tiled parallel execution for the current `OSM + single-ref` building runtime | supported |
| Benin canonical source profiling | supported |
| KG exposure for OpenBuildingMap / local Microsoft / Google Open Buildings | supported in KG, not executable |
| Google building-presence raster inspection and profiling | inspect-only |
| raster-based building height extraction | reserved |
| true 4-source building fusion semantics | reserved |

Benin preparation commands:

```powershell
python scripts/profile_benin_sources.py --source-root E:\fyx\data\Benin --output runs\benin-source-profile.json
python scripts/benchmark_tiled_building.py --source-root E:\fyx\data\Benin --bbox 2.48,9.23,2.77,9.44 --target-crs EPSG:32631 --output-root runs\benin-benchmark
```

Benin cleanup, profiling, and research scripts should be treated as bounded
research utilities or preparation capabilities. They do not, by themselves,
expand the stable main-runtime claim.

## Thesis Alignment Note

FusionAgent now distinguishes:

- executable core ontology: `Algorithm - Task - Data`
- scenario constraint layer: disaster event, `ScenarioProfile`, data need, output requirement, QoS policy

The runtime supports both `scenario-driven` and `task-driven` entry modes.
Direct task requests can bypass disaster inference and follow default task routing.

The current agent mode is best described as
`Constrained Plan-and-Execute with Reactive Healing`:
the LLM reasons inside KG-retrieved candidates and runtime constraints, while
validator, policy, audit, and healing loops bound correctness and robustness.

## Implemented Capabilities

### Core Runtime

- `planner -> validator -> executor -> healing/replan -> writeback`
- persisted `run.json`, `plan.json`, `validation.json`, and `audit.jsonl`
- persisted artifact bundle output
- explicit run status, decision records, and audit trail
- stable `building`, `road`, and `water` job support in the v2 runtime, plus a bounded `poi` slice
- dual-entry intent routing with `task-driven` / `scenario-driven` planning modes
- shared planning context via `TaskBundle` and `ScenarioProfile`

### Phase 1: Evaluation And Evidence Hardening

- `scripts/eval_harness.py` supports both golden-case and manifest modes
- harness summaries include commit SHA, base URL, timeout, mode, and environment
- manifest evaluation supports per-case timeout overrides
- manifest mode performs API and input preflight checks
- the real-data manifest still keeps the tracked-input `building_gitega_micro_agent` micro case for continuity with earlier evidence
- the real-data manifest now also includes `building_gitega_micro_msft_agent`, which materializes fresh-checkout inputs from official Geofabrik and Microsoft assets through `inputs.osm_source_id` and `inputs.reference_source_id`
- `scripts/materialize_source_assets.py` can prefetch those bounded source ids into `runs/source-assets/`
- docs now separate fast confidence checks from real evidence runs

### Phase 2: Search-Space Expansion

- broader disaster-specific workflow pattern coverage for `building` and `road`
- richer algorithm metadata: `accuracy_score`, `stability_score`, `usage_mode`
- richer data-source metadata: freshness, quality, and supported-type signals
- stronger parameter spec coverage with `tunable` and `optimization_tags`
- output schema policy metadata exposed through KG and planner retrieval

### Phase 3: Policy Coverage Expansion

- explicit decision types:
  - `pattern_selection`
  - `data_source_selection`
  - `artifact_reuse_selection`
  - `parameter_strategy`
  - `output_schema_policy`
  - `replan_or_fail`
- stable candidate evidence shape: `metrics + meta`
- decision traces persisted in both `run.json` and audit-backed status updates

### Phase 4: Artifact Reuse V2

- artifact registry with runtime direct reuse and clip reuse
- compatibility checks for:
  - `output_data_type`
  - `target_crs`
  - job-type freshness policy
- current freshness policy:
  - `building = 3d`
  - `road = 1d`
- clip reuse quality gates for CRS, required fields, and bbox safety
- explicit fallback to fresh execution when reuse is unsafe or materialization fails

### Phase 4.5: Task-Driven Input Acquisition

- `POST /api/v2/runs` accepts `input_strategy=task_driven_auto` for upload-free task-driven runs
- runtime resolves concrete `osm.zip` and `ref.zip` after planning chooses a usable data source
- natural-language region requests can now resolve an AOI first and inject `resolved_aoi` into both planner context and runtime input preparation
- input preparation reuses cached input bundles through version-token checks and bbox clip reuse
- resolved task inputs are written into audit evidence as `task_inputs_resolved`
- `aoi_resolved` and AOI-aware `task_inputs_resolved` events are both persisted into the audit trail
- the benchmark / eval path now has a bounded `SourceAssetService` fallback that can materialize `raw.osm.building / road / water / poi` and `raw.microsoft.building` from either repo-local `Data/` or an official download cache
- `RawVectorSourceService` now uses that source-asset fallback when local `Data/` is incomplete, so the task-driven runtime can continue through official cached downloads

### Phase 4.6: Source Catalog Expansion

- task-driven retrieval now distinguishes bundle-level sources from raw-vector sources
- building bundle sources now record concrete component pairs: `OSM + Google` and `OSM + Microsoft`
- road bundle sources now include an explicit `catalog.flood.road` route alongside earthquake and typhoon road bundles
- raw-vector catalog coverage now includes OSM `building / road / water / POI`, Microsoft buildings, Google buildings, local water samples, and open POI references already present under `Data/`
- planner retrieval exposes `component_source_ids`, `bundle_strategy`, `provider_family`, and local path hints for these sources

### Phase 4.7: Raw Source Download Chain

- task-driven runtime now materializes bundle inputs from raw-vector source specs instead of directly reading final bundle shapefiles
- raw-vector acquisition supports directory-first, exact-path, and recursive-glob locators from the shared source catalog
- raw sources are cached with version-aware reuse through the shared artifact registry before bundle assembly
- cached raw sources and cached input bundles both support bbox clip reuse
- clip reuse now transforms request-space bbox masks into the cached dataset CRS before clipping, so projected caches remain spatially correct
- `LocalBundleCatalogProvider` now assembles `osm.zip` and `ref.zip` from `component_source_ids`, while single-source road bundles generate an empty reference bundle on demand
- the runtime path can now also fall back to `SourceAssetService` when local catalog inputs are missing, so official Geofabrik / Microsoft assets can be downloaded, clipped, and bundled in the live task-driven flow
- `scripts/smoke_agentic_region.py` provides the standard smoke entry for natural-language region runs, with Nairobi, Kenya as the recommended validation example

### Phase 4.8: Trajectory-To-Road Seam Reservation

- the KG now reserves a transform seam `dt.trajectory.raw -> dt.road.candidate -> dt.road.bundle` for future trajectory pretransform work
- planner retrieval now exposes reserved metadata such as `task.trajectory_to_road` and `algo.transform.trajectory_to_road_candidate`
- this remains reservation-only in the current runtime: default road execution still starts from `dt.road.bundle`, and there is no live trajectory ingestion, map matching, or road-candidate inference in Phase 4

### Phase 5: Long-Term Writeback And Learning Loop

- each run writes a compact `DurableLearningRecord`
- durable records now retain planning metadata such as planning mode, profile source, and task bundle
- durable records are stored separately from verbose audit logs
- repositories can aggregate outcome evidence by:
  - pattern
  - algorithm
  - data source
- planner retrieval now exposes durable learning summaries

### Phase 6: Productization And Operations

- operator inspection endpoint:
  - `GET /api/v2/runs/{run_id}/inspection`
- run comparison endpoint:
  - `GET /api/v2/runs/{left_run_id}/compare/{right_run_id}`
- cleaned `docs/v2-operations.md` covering runtime conventions and operator flows

### Phase F: Water Vertical Slice

- added the `water` polygon fusion vertical slice onto the shared runtime backbone
- planner, KG seed, executor dispatch, adapter output, artifact writeback, and Neo4j bootstrap are now closed for this slice
- `water` supports `task_driven_auto` after Phase 1 stabilization and now shares the same evidence contract as `building` and `road`
- tracked implementation record: [2026-04-20-water-vertical-slice.md](./docs/superpowers/plans/done/2026-04-20-water-vertical-slice.md)

### Phase F.1: POI Vertical Slice

- the bounded `poi` automatic-fusion slice is now connected to the shared runtime backbone
- its current scope remains intentionally narrow: `raw.osm.poi + raw.gns.poi -> catalog.generic.poi -> algo.fusion.poi.v1`
- planner, KG seed, executor dispatch, task-driven input acquisition, adapter output, and Neo4j bootstrap now form a first closed loop for this slice
- this should be described as deterministic and bounded, not as proof of general multi-source POI entity resolution

### Phase G: Experiment Matrix And Paper Evidence Freeze

- manifest-mode `scripts/eval_harness.py` output now preserves matrix-ready metadata and evidence fields
- added `scripts/freeze_paper_evidence.py` to normalize both harness summary JSON and historical single-case durable result JSON into frozen paper-facing JSON and Markdown
- tracked Phase G artifacts include:
  - [paper experiment matrix](./docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json)
  - [paper evidence freeze JSON](./docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json)
  - [paper evidence freeze Markdown](./docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md)

### Phase H: Scenario Evidence And Reporting

- added `POST /api/v2/scenario-runs` to orchestrate multiple `task_driven_auto` child runs from one scenario request, such as building + road disaster response
- scenario output roots resolve from request `output_root`, then `GEOFUSION_SCENARIO_OUTPUT_ROOT`, then `E:\fyx\data\fusionagentTEST`
- scenario evidence adds `scenario_summary.json`, `kg_path_trace.json`, `workflow_trace.json`, `source_coverage.json`, and `evaluation.json`
- bilingual Markdown reports are written to `documents/scenario_report.zh.md` and `documents/scenario_report.en.md`
- scenario summaries expose KG relationship chains, actual workflow traces, source coverage / fallback evidence, data-fusion metrics, agentic metrics, and self-evolution evidence

## Evidence Written Per Run

Each run currently persists the following core evidence files:

- `run.json`
- `plan.json`
- `validation.json`
- `audit.jsonl`
- artifact bundle

Scenario-level runs additionally persist:

- `scenario_summary.json`
- `kg_path_trace.json`
- `workflow_trace.json`
- `source_coverage.json`
- `evaluation.json`
- `documents/scenario_report.zh.md`
- `documents/scenario_report.en.md`

## Known Remaining Gaps

Even after reaching no-UI maturity, these product and research boundaries still
remain:

- the final product-grade frontend and final visualization shape are still not
  complete; the current operator surface now includes a web workbench
  foundation, but it is still focused on run inspection, evidence browsing,
  and settings management
- external provider event feeds are not integrated
- production deployment, auth, multi-tenant isolation, and full production
  operations are not claimed
- no claim of 7x24 production operation, arbitrary off-domain request support,
  or final UI completion
- the search space still focuses on the current `building`, `road`, `water`, and bounded `poi` themes
- `water` and bounded `poi` now sit on the shared task-driven backbone, but
  that should not be overstated as proof that arbitrary new task families are
  already free to extend
- the trajectory-to-road path is only a seam reservation today and must not be described as already supporting real trajectory ingestion, live trajectory-to-road ingestion, or road inference
- durable learning is still a first-pass capability, not full policy auto-tuning
- `raw.google.building` and some local-only reference / Excel-style inputs still require manual preparation and are not part of the current official materialization set
- AOI resolution still depends on an external geocoder, so availability and latency remain sensitive to network conditions

## Repository Structure

- `api/`: FastAPI routes and app entry points
- `services/`: runtime services, including `AgentRunService`
- `agent/`: planner, retriever, validator, executor, and policy logic
- `kg/`: KG models, repositories, seed data, and bootstrap logic
- `adapters/`: building, road, water, and poi fusion adapters
- `worker/`: Celery worker and scheduling entry points
- `llm/`: LLM provider abstractions and implementations
- `scripts/`: harness, paper evidence freeze, bootstrap, local start, and inspection scripts
- `tests/`: unit, integration, runtime, API, and repository tests
- `docs/`: operations and design documentation

## Running Locally

### Fast Local Mode

Use this for unit tests, API contract checks, and local debugging.

```powershell
python -m pip install -r requirements.txt
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Full Local Loop

Use this for Neo4j, Redis, Celery, and live-LLM integration.

```powershell
python scripts/start_local.py --check-only
python scripts/start_local.py --port 8000
python scripts/smoke_agentic_region.py --base-url http://127.0.0.1:8000 --query "fuse building and road data for Nairobi, Kenya" --timeout 1200
```

Local runtime conventions:

- use `8000` as the default port for everyday development, smoke runs, and manual debugging
- the standard full-loop startup command is `python scripts/start_local.py --port 8000`
- local direct-run entrypoints load the repo-root `依赖.txt` first; Redis broker / backend should follow its `Redis端口`, and the repo example currently uses `6380`
- Celery falls back to the generic code default `redis://localhost:6379/0` only when no `依赖.txt`-derived value is available
- the default Neo4j convention is `bolt://localhost:7687`
- reserve `8011` for isolated fast-confidence checks
- reserve `8010` for isolated real-data benchmarks
- use `8012+` only for temporary diagnostics, not as a standing default port

To reset the managed graph during setup checks:

```powershell
python scripts/start_local.py --check-only --reset-managed-graph
```

### Frontend Workbench

Use this for local UI development and API integration.

Terminal A:

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Terminal B:

```powershell
Set-Location frontend
npm install
npm run dev
```

Conventions:

- default Vite entrypoint: `http://127.0.0.1:5173/`
- the frontend defaults to Simplified Chinese, with an `English` switch in the sidebar
- the Vite dev server proxies `/api` to `http://127.0.0.1:8000`
- FastAPI allows `http://127.0.0.1:5173` and `http://localhost:5173` by default; override with `GEOFUSION_CORS_ORIGINS` when needed

To serve the built frontend from FastAPI on the same origin:

```powershell
Set-Location frontend
npm run build
Set-Location ..
uvicorn main:app --host 127.0.0.1 --port 8000
```

After the build, open `http://127.0.0.1:8000/`. Any non-`/api/*` route falls
back to `frontend/dist/index.html`, so direct navigation to SPA routes works.

### Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Notes:

- the `docker compose` path uses container-local `redis://redis:6379/0` and API port `8000`
- it does not depend on the local Redis port declared in `依赖.txt`

## Evaluation Tiers

### Tier 1: Targeted Tests

For the focused system-next regression set, run:

```powershell
python -m pytest -q tests/test_tool_registry.py tests/test_plan_grounding_service.py tests/test_unsupported_intent_guard.py tests/test_run_telemetry_service.py tests/test_run_recovery_service.py tests/test_eval_kg_ablation.py
```

Use for everyday regression checking.

### Tier 2: Golden-Case Harness

Use for API-to-runtime closed-loop checks.

### Tier 3: Real-Data Benchmark

Use for durable research evidence.

Current timeout guidance:

- harness default: `180s`
- real-data building benchmarks should not be judged with `180s`
- current recommendation for real-data building runs: at least `1200s`
- `building_gitega_micro_agent` remains the tracked-input micro benchmark for historical alignment
- `building_gitega_micro_msft_agent` is now reproducible on a fresh checkout from official source ids and has been re-verified on an isolated `8010` full-loop runtime; tracked evidence lives in `docs/superpowers/specs/2026-04-16-building-micro-msft-fresh-checkout-result.json`
- if you want to warm the fresh-checkout cache first, run `python scripts/materialize_source_assets.py --source raw.osm.building --source raw.microsoft.building --bbox 29.817351,-3.646572,29.931113,-3.412421 --prefer-remote`
- `scripts/eval_harness.py` now prefers non-sensitive runtime metadata from `/api/v2/runtime`, so saved summary `environment` fields reflect the actual runtime more reliably than shell-only env capture

## Common Verification Commands

Run the full test suite:

```powershell
python -m pytest -q
```

Common runtime-focused subset:

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
python -m pytest -q `
  tests/test_planner_context.py `
  tests/test_agent_run_service_enhancements.py `
  tests/test_input_acquisition_service.py `
  tests/test_source_asset_service.py `
  tests/test_raw_vector_source_service.py `
  tests/test_local_bundle_catalog.py `
  tests/test_eval_harness.py `
  tests/test_policy_engine.py `
  tests/test_artifact_registry.py `
  tests/test_parameter_binding.py `
  tests/test_planner_artifact_reuse.py `
  tests/test_agent_state_models.py `
  tests/test_kg_parameter_specs.py `
  tests/test_neo4j_bootstrap.py `
  tests/test_neo4j_repository.py `
  tests/test_api_v2_integration.py
```

## v2 API

### Create Run

- `POST /api/v2/runs`
- use uploaded bundles by default, or set `input_strategy=task_driven_auto` to let the shared runtime prepare inputs automatically for `building`, `road`, `water`, and bounded `poi`

### Create Scenario Run

- `POST /api/v2/scenario-runs`
- use this for scenario-level orchestration and report generation; it does not replace the single-run API
- output directories follow `output_root -> GEOFUSION_SCENARIO_OUTPUT_ROOT -> E:\fyx\data\fusionagentTEST`

### Inspect Run State And Evidence

- `GET /api/v2/runs/{run_id}`
- `GET /api/v2/runs/{run_id}/plan`
- `GET /api/v2/runs/{run_id}/audit`
- `GET /api/v2/runs/{run_id}/artifact`
- `GET /api/v2/runs/{run_id}/inspection`
- `GET /api/v2/runs/{left_run_id}/compare/{right_run_id}`

## Recommended Reading

- [docs/v2-operations.md](docs/v2-operations.md)
- [docs/superpowers/specs/2026-04-07-fusion-agent-v2-design.md](docs/superpowers/specs/2026-04-07-fusion-agent-v2-design.md)
- [docs/superpowers/plans/done/2026-04-07-fusion-agent-v2-implementation.md](docs/superpowers/plans/done/2026-04-07-fusion-agent-v2-implementation.md)
- [docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md](docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md)
- [docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json](docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json)
- [docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md](docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md)

## Notes

- do not commit `.env`, runtime logs, `runs/`, `jobs/`, or other local artifacts
- do not commit private local dependency files
- keep text files in UTF-8 to avoid encoding corruption
