# FusionAgent

FusionAgent is a vector-data fusion agent prototype for disaster response workflows.
The current `main` branch is no longer just a script wrapper. It now provides a
testable, auditable, and incrementally extensible agentic workflow runtime.

The runtime currently supports `building` and `road` jobs using uploaded
`zip shapefile` inputs, and can perform planning, validation, execution,
healing, replanning, evidence writeback, and artifact output.

## Current Position

The most accurate description of the project today is:

- engineering MVP: reached
- research-grade iterative prototype: reached
- final product form: not reached

FusionAgent already has a credible runtime loop, but it is still not the final
long-lived product form with a full operator UI and mature long-term learning.

## Implemented Capabilities

### Core Runtime

- `planner -> validator -> executor -> healing/replan -> writeback`
- persisted `run.json`, `plan.json`, `validation.json`, and `audit.jsonl`
- persisted artifact bundle output
- explicit run status, decision records, and audit trail
- `building` and `road` job support in the v2 runtime

### Phase 1: Evaluation And Evidence Hardening

- `scripts/eval_harness.py` supports both golden-case and manifest modes
- harness summaries include commit SHA, base URL, timeout, mode, and environment
- manifest evaluation supports per-case timeout overrides
- manifest mode performs API and input preflight checks
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

### Phase 5: Long-Term Writeback And Learning Loop

- each run writes a compact `DurableLearningRecord`
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
python scripts/start_local.py
```

To reset the managed graph during setup checks:

```powershell
python scripts/start_local.py --check-only --reset-managed-graph
```

### Docker Compose

```powershell
Copy-Item .env.example .env
docker compose up --build
```

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
