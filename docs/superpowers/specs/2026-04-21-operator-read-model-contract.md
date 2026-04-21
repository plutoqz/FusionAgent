# Operator Read-Model Contract

## Purpose

This contract defines the no-UI operator read model that sits between the mature no-UI agent runtime and any future visualization interface. It gives operators and future UI clients stable summary and list surfaces for persisted runs, scenario runs, runtime configuration signals, and explicit evidence gaps without requiring direct inspection of raw output directories.

The contract is intentionally read-only. It describes what a future UI may consume, not the final UI itself.

## Current Surfaces

### `GET /api/v2/runs`

Returns an `OperatorRunListResponse` from `schemas/operator.py`.

Shape:

```json
{
  "records": [
    {
      "run_id": "run-a",
      "phase": "succeeded",
      "job_type": "building",
      "run_dir": "C:/.../runs/run-a"
    }
  ]
}
```

Contract notes:

- `records` is a list of persisted single-run records read from the runs registry.
- Each record is a dictionary to preserve compatibility with existing `run.json` payloads.
- `run_dir` is added by `RunRegistryService` as an operator navigation hint.
- Query filters may include `limit`, `phase`, and `job_type`.
- The endpoint is for listing. Detailed inspection remains on the existing run inspection surface.

### `GET /api/v2/operator/summary`

Returns an `OperatorRuntimeSummaryResponse` from `schemas/operator.py`.

Shape:

```json
{
  "runtime": {
    "kg_backend": "neo4j",
    "llm_provider": "openai",
    "celery_eager": "1",
    "api_port": "8000"
  },
  "recent_runs": [],
  "recent_scenarios": [],
  "evidence_gaps": [
    "No persisted runs found."
  ]
}
```

Contract notes:

- `runtime` exposes selected environment-derived operator signals only.
- `recent_runs` is populated from the persisted single-run registry.
- `recent_scenarios` is populated from the scenario registry.
- `evidence_gaps` is a first-class field for missing run or scenario evidence rather than an implicit failure hidden in logs.
- `limit` bounds the number of recent run and scenario records returned.

## Data Sources

### Runs Registry

`services/run_registry_service.py` scans persisted `runs/*/run.json` records, sorts by `run.json` modification time descending, applies optional `phase` and `job_type` filters, and returns read-only dictionaries. Invalid JSON or unreadable records are skipped rather than treated as successful evidence.

### Scenario Registry

`services/scenario_registry_service.py` reads the scenario index under the configured scenario output root. The operator summary uses it for recent scenario visibility and for detecting whether scenario evidence exists at all.

### Runtime Environment

`services/operator_read_model_service.py` exposes selected runtime settings such as KG backend, LLM provider, Celery eager mode, and API port. These values are operational context, not a security or deployment attestation.

### Evidence Gaps

Evidence gaps are explicit strings produced when persisted run or scenario records are missing. Future UI clients should render these as operator-facing readiness gaps rather than treating empty lists as silent success.

## Future UI Consumption Boundary

Future UI work may consume these read models as stable no-UI summaries:

- A run list page can use `/api/v2/runs` as the source of persisted single-run rows.
- A runtime overview page can use `/api/v2/operator/summary` for recent runs, recent scenarios, runtime context, and gaps.
- UI navigation can link from run rows to existing inspection and comparison APIs.
- UI status panels should preserve `evidence_gaps` wording or map it to equivalent operator-facing warnings.

Future UI work must not assume these surfaces provide write operations, authentication state, live streaming progress, or complete production observability.

## Stability

Stable for no-UI maturity:

- Endpoint paths: `/api/v2/runs` and `/api/v2/operator/summary`.
- Top-level response fields: `records`, `runtime`, `recent_runs`, `recent_scenarios`, and `evidence_gaps`.
- Read-only behavior over persisted local records.
- Explicit evidence-gap reporting for missing run or scenario evidence.

Flexible until final UI work:

- Additional dictionary keys inside run and scenario records.
- Additional runtime signal keys.
- More evidence-gap messages.
- Additional filters that do not break existing query behavior.

## Non-Goals

- This is not the final visualization UI.
- This is not a write API for creating, mutating, retrying, or deleting runs.
- This is not production authentication, authorization, tenancy, audit retention, or SaaS readiness.
- This is not a replacement for detailed run inspection, run comparison, scenario inspection, or frozen evidence artifacts.
- This does not claim external event-feed integration or live trajectory-to-road ingestion.
