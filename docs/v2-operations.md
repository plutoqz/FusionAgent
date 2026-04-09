# FusionAgent v2 Operations

## Current Position

`v2` is the current agentic runtime line in this repo. It is not a full product surface yet, but it now has:

- explicit planning, validation, execution, healing, and writeback stages
- persisted `run.json`, `plan.json`, `validation.json`, and `audit.jsonl`
- durable learning summaries for long-term planning evidence
- operator-facing inspection and comparison endpoints in the v2 API

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

## Evaluation Tiers

### Tier 1: Targeted Tests

Use this for everyday development and regression control.

Minimum evidence:

- exact `pytest` command
- pass or fail output
- failing test names when red

### Tier 2: Golden-Case Harness

Use this when you need an API-to-runtime closed loop without paying the cost of a real-data benchmark.

Minimum evidence:

- saved harness summary JSON
- failed `case_id`
- related `run_id` when available

### Tier 3: Real-Data Benchmark

Use this only when you need durable research evidence.

Minimum evidence:

- saved benchmark summary JSON
- `run_id`
- matching `run.json`, `plan.json`, `audit.jsonl`, and artifact bundle
- `base_url`, timeout, and key environment notes

## Timeout Guidance

- `scripts/eval_harness.py` still defaults to `180` seconds
- that default is acceptable for fast confidence checks, not for real building benchmarks
- current real-data building runs should use an explicit timeout such as `1200`
- when a benchmark times out, verify timeout policy and runtime alignment before blaming the algorithm

## Recommended Commands

### Fast Confidence

Terminal A:

```powershell
$env:GEOFUSION_KG_BACKEND='memory'
$env:GEOFUSION_LLM_PROVIDER='mock'
$env:GEOFUSION_CELERY_EAGER='1'
uvicorn main:app --host 127.0.0.1 --port 8011
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
  --base-url http://127.0.0.1:8011 `
  --timeout 180 `
  --case building_disaster_flood `
  --case road_disaster_earthquake `
  --output-json tmp/eval/fast-confidence-summary.json
```

### Real Evidence

```powershell
python scripts/eval_harness.py `
  --manifest docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json `
  --case building_gitega_osm_vs_google_agent `
  --case building_gitega_osm_vs_msft_clipped_agent `
  --base-url http://127.0.0.1:8010 `
  --timeout 1200 `
  --output-json tmp/eval/real-evidence-summary.json
```

## Operator Inspection API

The v2 API now has a narrow but practical operator layer.

### Single Run Inspection

- `GET /api/v2/runs/{run_id}`: raw run status
- `GET /api/v2/runs/{run_id}/plan`: persisted plan
- `GET /api/v2/runs/{run_id}/audit`: full audit event stream
- `GET /api/v2/runs/{run_id}/artifact`: artifact bundle download
- `GET /api/v2/runs/{run_id}/inspection`: one-shot operational view of status, plan, audit events, and artifact metadata

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
