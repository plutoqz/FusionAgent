# FusionAgent

[中文说明](./README.md)

FusionAgent is a vector-data fusion agent prototype for disaster response workflows.
The current `main` branch is no longer just a script wrapper. It now provides a
testable, auditable, and incrementally extensible agentic workflow runtime.

The runtime currently supports `building` and `road` jobs using either uploaded
`zip shapefile` inputs or task-driven auto-acquired input bundles, and can
perform planning, validation, execution, healing, replanning, evidence
writeback, and artifact output.

## Current Position

The most accurate description of the project today is:

- engineering MVP: reached
- research-grade iterative prototype: reached
- final product form: not reached

FusionAgent already has a credible runtime loop, but it is still not the final
long-lived product form with a full operator UI and mature long-term learning.

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
- `building` and `road` job support in the v2 runtime
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

## Evidence Written Per Run

Each run currently persists the following core evidence files:

- `run.json`
- `plan.json`
- `validation.json`
- `audit.jsonl`
- artifact bundle

## Known Remaining Gaps

Even though the six roadmap phases are implemented, there are still clear gaps:

- benchmark evidence is not yet promoted into a more durable tracked research note
- the search space still focuses on the current `building` and `road` themes
- durable learning is still a first-pass capability, not full policy auto-tuning
- operator-facing productization is still a narrow API layer, not a full frontend
- `raw.google.building` and some local-only reference / Excel-style inputs still require manual preparation and are not part of the current official materialization set
- AOI resolution still depends on an external geocoder, so availability and latency remain sensitive to network conditions

## Repository Structure

- `api/`: FastAPI routes and app entry points
- `services/`: runtime services, including `AgentRunService`
- `agent/`: planner, retriever, validator, executor, and policy logic
- `kg/`: KG models, repositories, seed data, and bootstrap logic
- `adapters/`: building and road fusion adapters
- `worker/`: Celery worker and scheduling entry points
- `llm/`: LLM provider abstractions and implementations
- `scripts/`: harness, bootstrap, local start, and inspection scripts
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
- use uploaded bundles by default, or set `input_strategy=task_driven_auto` to let the runtime prepare inputs automatically

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
- [docs/superpowers/plans/2026-04-07-fusion-agent-v2-implementation.md](docs/superpowers/plans/2026-04-07-fusion-agent-v2-implementation.md)
- [docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md](docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md)

## Notes

- do not commit `.env`, runtime logs, `runs/`, `jobs/`, or other local artifacts
- do not commit private local dependency files
- keep text files in UTF-8 to avoid encoding corruption
