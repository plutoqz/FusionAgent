# FusionAgent

[中文说明](./README.md)

Resume/demo brief: [FusionAgent Resume Project Brief](./docs/demo/fusionagent-resume-project-brief.md).

FusionAgent is a bounded geospatial vector-fusion agent runtime for disaster-response workflows. This repository contains the backend runtime, knowledge-graph constraint layer, task and scenario orchestration, evidence writeback pipeline, and an operator-facing web workbench.

The project is not positioned as an unbounded general-purpose agent. Its goal is to turn task understanding, input acquisition, constrained planning, fusion execution, failure healing, and evidence preservation into a testable and auditable engineering system.

FusionAgent can now run as a mature no-UI vector data fusion agent: the no-UI operator surface, scenario regression, maturity freeze, and shared evidence contract are aligned behind one regression-tested execution path.

## Current Evidence Snapshot

- The Track A / Track B master plan is complete and archived at `docs/superpowers/plans/done/2026-05-13-fusionagent-master-execution-plan.md`.
- Track B national-scale evidence is frozen in `docs/superpowers/specs/2026-05-18-track-b-national-scale-evidence-freeze.json`, with `road`, `water`, and `poi` all recorded as `national_scale_supported`.
- The current road full-closure contract targets `raw.osm.road + raw.microsoft.road`. The older `raw.overture.transportation` freeze is retained as historical compatibility evidence only, not as the promoted second source.

## What This Repository Contains

The current codebase provides:

- support for `building`, `road`, `water`, and bounded `poi` fusion tasks
- two input modes:
  - uploaded `osm.zip` / `ref.zip`
  - `task_driven_auto` input acquisition
- both single-run and scenario-run execution
- persisted run artifacts, audit trails, scenario reports, and preview GeoJSON outputs
- operator capabilities for inspection, comparison, KG overview, and LLM settings

## Scope

FusionAgent is intended for:

- bounded disaster-response vector fusion with explicit task types and output goals
- research prototypes or engineering MVPs that need planning, validation, execution, and evidence traces
- local reproducible runs, regression checks, and scenario reporting

It is not currently positioned as:

- an open-domain general-purpose agent
- a final product-grade visualization platform
- a production-grade multi-tenant deployment and 24x7 operations system
- an unbounded source-ingestion or arbitrary task-expansion framework

## Technical Approach

### Runtime Method

The runtime follows a constrained `Plan-and-Execute with Reactive Healing` flow:

1. `planner` builds candidates from the task, scenario, KG, and source catalog
2. `validator` checks plan validity, parameters, inputs, and scope boundaries
3. `executor` dispatches concrete fusion algorithms and input-preparation steps
4. `healing / replan` performs bounded recovery when execution or validation fails
5. `writeback` persists run state, plan, audit logs, artifacts, and scenario evidence

### Knowledge and Data Method

- a knowledge graph models tasks, algorithms, data sources, output constraints, and scenario relations
- source catalog, artifact registry, and AOI resolution support task-driven input preparation
- a shared evidence contract stabilizes run-level and scenario-level outputs
- operator read models, reports, and GeoJSON previews support inspection and review

### Evidence Contract

A single run writes:

- `run.json`
- `plan.json`
- `validation.json`
- `audit.jsonl`
- artifact bundle

A scenario run additionally writes:

- `scenario_summary.json`
- `kg_path_trace.json`
- `workflow_trace.json`
- `source_coverage.json`
- `evaluation.json`
- `documents/scenario_report.zh.md`
- `documents/scenario_report.en.md`

## Architecture

### Backend Runtime

- `FastAPI` for the `v1` / `v2` APIs
- `Celery + Redis` for worker and scheduler execution
- `Neo4j` or in-memory KG backend
- `Pydantic` for runtime schemas and contracts

### GIS and Fusion Stack

- `GeoPandas`
- `Shapely`
- `Fiona`
- `PyProj`
- `Rasterio`
- `NetworkX`
- `SciPy`
- `NumPy`
- `Pandas`

### Operator Frontend

- `React 18`
- `Vite`
- `TypeScript`
- `React Router`
- `TanStack Query`
- `MapLibre GL`
- `Cytoscape`

## Repository Layout

```text
fusionAgent/
├─ agent/                 # planner / executor / retriever and runtime core
├─ api/                   # FastAPI app and routers
├─ frontend/              # React + Vite operator workbench
├─ kg/                    # knowledge graph bootstrap and query logic
├─ services/              # orchestration, scenario, settings, and preview services
├─ schemas/               # Pydantic schemas and response models
├─ scripts/               # local startup, smoke, evaluation, and evidence scripts
├─ tests/                 # unit tests, integration tests, golden cases
├─ docs/                  # operations docs, specs, plans, notes
├─ worker/                # Celery app and background tasks
├─ Data/                  # local raw and reference data
└─ runs/                  # local runtime outputs and logs
```

## Prerequisites

Recommended local environment:

- Python 3.9 - 3.11
- Node.js and npm for frontend development
- Redis
- Neo4j 5.x
- PowerShell 7 or another usable shell

Install Python dependencies:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Install frontend dependencies:

```powershell
Set-Location frontend
npm install
Set-Location ..
```

## Configuration

The repository provides two local configuration entry points:

- [依赖.txt.example](./依赖.txt.example): private local dependency template for direct local runs
- [.env.example](./.env.example): environment variable example

Recommended first step:

```powershell
Copy-Item 依赖.txt.example 依赖.txt
```

`依赖.txt` is typically used for local Redis, Neo4j, and LLM connection settings. `scripts/start_local.py`, `main.py`, and `worker/celery_app.py` read it before falling back to generic defaults.

## Local Deployment Options

### Option A: Fast Mode

Use this for API checks, unit tests, frontend development, and lightweight smoke runs.

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
uvicorn main:app --host 127.0.0.1 --port 8000
```

Frontend development:

```powershell
Set-Location frontend
npm run dev
```

The default frontend dev URL is `http://127.0.0.1:5173`, and FastAPI allows the local dev origin by default.

### Option B: Full Local Runtime

Use this when Redis, Neo4j, worker, scheduler, and live LLM settings all need to participate.

Run dependency and Neo4j checks first:

```powershell
python scripts/start_local.py --check-only
```

Then start the full local loop:

```powershell
python scripts/start_local.py --port 8000
```

Default behavior:

- API starts at `http://127.0.0.1:8000`
- logs are written under `runs/local-runtime/`
- API, worker, and scheduler processes are started together
- when the KG backend is `neo4j`, local seed checks and bootstrap are performed automatically
- startup summary prints the active `Neo4j database` and `Neo4j namespace guard`

Recommended Neo4j isolation order:

1. one Neo4j instance or port per project
2. keep `GEOFUSION_GRAPH_NAMESPACE=fusionagent` as an application-level second guard
3. do not use a miscellaneous shared graph view for paper-evidence runs

### Option C: Same-Origin Frontend Serving

If `frontend/dist/` exists, FastAPI serves the built frontend automatically.

```powershell
Set-Location frontend
npm run build
Set-Location ..
uvicorn main:app --host 127.0.0.1 --port 8000
```

### Option D: Docker Compose

The repository includes a full container orchestration setup:

```powershell
docker compose up --build
```

By default it starts:

- `api`
- `worker`
- `scheduler`
- `redis`
- `neo4j`

Default ports:

- API: `8000`
- Redis: `6379`
- Neo4j HTTP: `7474`
- Neo4j Bolt: `7687`

Container mode uses `redis://redis:6379/0` and `bolt://neo4j:7687`, which is separate from the host-side `依赖.txt` convention.

## API Overview

### Runs and Inspection

- `GET /api/v2/runs`
- `POST /api/v2/runs`
- `GET /api/v2/runs/{run_id}`
- `GET /api/v2/runs/{run_id}/plan`
- `GET /api/v2/runs/{run_id}/audit`
- `GET /api/v2/runs/{run_id}/inspection`
- `GET /api/v2/runs/{run_id}/kg-graph`
- `GET /api/v2/runs/{run_id}/preview`
- `GET /api/v2/runs/{run_id}/preview.geojson`
- `GET /api/v2/runs/{run_id}/artifact`
- `GET /api/v2/runs/{left_run_id}/compare/{right_run_id}`

### Runtime and Overview

- `GET /api/v2/runtime`
- `GET /api/v2/operator/summary`
- `GET /api/v2/kg/overview`

### Scenario Runs

- `GET /api/v2/scenario-runs`
- `POST /api/v2/scenario-runs`
- `GET /api/v2/scenario-runs/{scenario_id}`
- `GET /api/v2/scenario-runs/{scenario_id}/documents`
- `GET /api/v2/scenario-runs/{scenario_id}/documents/{filename}`

### LLM Settings

- `GET /api/v2/settings/llm`
- `PUT /api/v2/settings/llm`
- `POST /api/v2/settings/llm/validate`

## Validation and Tests

Backend tests:

```powershell
python -m pytest -q
```

Frontend tests:

```powershell
Set-Location frontend
npm test
Set-Location ..
```

Local run smoke:

```powershell
python scripts/smoke_local_v2.py --base-url http://127.0.0.1:8000
```

Task-driven AOI smoke:

```powershell
python scripts/smoke_agentic_region.py --base-url http://127.0.0.1:8000 --job-type building --query "fuse building data for Nairobi, Kenya" --timeout 1200
```

## Current Boundaries

To keep project claims accurate:

- `poi` remains intentionally bounded and should not be described as general multi-source entity resolution
- trajectory-to-road is only a reserved seam, not a live execution path
- external event ecosystems, production auth, multi-tenant governance, and long-term autonomous learning are outside the current delivery scope
- the frontend workbench is an operator surface, not the final product UI

## References

- [docs/v2-operations.md](./docs/v2-operations.md)
- [docs/local-direct-run.md](./docs/local-direct-run.md)
- [docs/no-ui-agent-operations.md](./docs/no-ui-agent-operations.md)
- [docs/demo/fusionagent-resume-project-brief.md](./docs/demo/fusionagent-resume-project-brief.md)
