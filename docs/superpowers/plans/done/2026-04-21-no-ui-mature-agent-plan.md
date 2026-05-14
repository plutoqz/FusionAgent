# No-UI Mature Vector Fusion Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status Note:** Partially superseded by `docs/superpowers/plans/2026-05-12-fusionagent-master-execution-plan.md` on 2026-05-12. Do not treat the full checklist below as the current active backlog. Only operator, evidence, maturity-check, and runbook closures that are still unevidenced belong to the current Phase 3 review path; existing artifacts such as `docs/no-ui-agent-operations.md`, `docs/superpowers/specs/2026-04-21-operator-read-model-contract.md`, `docs/superpowers/specs/2026-04-21-no-ui-maturity-target.md`, `docs/superpowers/specs/2026-04-21-no-ui-maturity-gap-ledger.md`, and `docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.*` should be treated as already-landed evidence unless fresh drift proves otherwise.

**Goal:** Promote FusionAgent from a research prototype with strong evidence into a mature no-UI vector data fusion agent that is defensible for paper research and practical engineering use before any final visualization interface is built.

**Architecture:** Keep the final frontend out of scope. Mature the system through claim discipline, scenario-driven autonomy, reproducible source acquisition, artifact/evidence products, operator read APIs, local operations hardening, and a final maturity freeze. Existing runtime execution stays centered on `services/agent_run_service.py`, scenario orchestration stays centered on `services/scenario_run_service.py`, and new work should wrap those services rather than duplicating planner/executor orchestration.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic, pytest, GeoPandas, existing v2 runtime services, JSON/Markdown evidence artifacts, file-backed local registries, existing scenario harness and evidence freeze scripts.

---

## Scope Definition

This plan defines the remaining work before the final visual interface. After completing it, the project may be described as a mature no-UI disaster-response vector data fusion agent with natural-language and scenario-triggered entry points, KG-constrained planning, task-driven data acquisition, execution/replan/learning evidence, reproducible scenario and benchmark evaluation, operator-grade read APIs, and documented local operations.

The project must still not claim:

- a completed frontend product
- production SaaS readiness
- arbitrary new geospatial task support
- live trajectory-to-road ingestion
- full autonomous policy auto-tuning
- external event-feed integration beyond the documented local trigger inbox

## Phase 0: Documentation Discovery

Read these before implementation:

- `README.md`
- `README.en.md`
- `docs/v2-operations.md`
- `docs/superpowers/specs/2026-04-20-final-gap-matrix.md`
- `docs/superpowers/specs/2026-04-20-evidence-ledger.md`
- `docs/superpowers/specs/2026-04-20-long-chain-decision-roadmap.md`
- `docs/superpowers/specs/2026-04-20-evaluation-contract-claim-lock.md`
- `docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json`
- `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md`
- `docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json`
- `docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md`
- `api/routers/runs_v2.py`
- `api/routers/scenario_runs.py`
- `schemas/agent.py`
- `schemas/scenario.py`
- `schemas/scenario_manifest.py`
- `services/agent_run_service.py`
- `services/scenario_run_service.py`
- `services/scenario_registry_service.py`
- `services/scenario_trigger_service.py`
- `services/source_asset_service.py`
- `services/aoi_resolution_service.py`
- `services/artifact_evaluation_service.py`
- `scripts/eval_harness.py`
- `scripts/scenario_eval_harness.py`
- `scripts/freeze_paper_evidence.py`
- `scripts/freeze_scenario_evidence.py`
- `scripts/watch_scenario_inbox.py`

Allowed APIs and patterns:

- Use `ScenarioRunRequest`, `ScenarioRunResponse`, `ScenarioRunListResponse`, and `ScenarioRunInspectionResponse` from `schemas/scenario.py`.
- Use `scenario_run_service.create_scenario_run(request)` for in-process scenario orchestration.
- Use `POST /api/v2/scenario-runs` for API-level scenario orchestration.
- Use `GET /api/v2/scenario-runs` and `GET /api/v2/scenario-runs/{scenario_id}` for scenario listing and inspection.
- Use `GET /api/v2/runs/{run_id}/inspection`, `GET /api/v2/runs/{left_run_id}/compare/{right_run_id}`, and `GET /api/v2/runtime` as the existing single-run operator surface.
- Use `normalize_trigger_event(event)` from `services/scenario_trigger_service.py` for file-inbox event normalization.
- Use `process_inbox_once(inbox_dir, processed_dir, output_root=None)` from `scripts/watch_scenario_inbox.py` as the current local event-trigger entry point.
- Use `SourceAssetService.resolve_raw_source_path(source_id, request_bbox=request_bbox, aoi=resolved_aoi)` for official/local source materialization.
- Use `evaluate_vector_artifact(shp_path, required_fields=required_fields)` and `evaluate_agentic_run(plan=plan, decision_records=decision_records, audit_events=audit_events, durable_learning_summary=summary, manual_intervention_count=0)` from `services/artifact_evaluation_service.py` for artifact and agentic evidence.

Anti-pattern guards:

- Do not build the final UI in this plan.
- Do not duplicate `AgentRunService` planning, validation, execution, or repair orchestration.
- Do not make `partial` mean success without capability evidence.
- Do not promote water or POI to execution-level scenario claims until source materialization evidence supports it.
- Do not describe `trajectory-to-road` as a live runtime path.
- Do not rely on untracked `runs/` or `Data/` directories as final paper evidence without a frozen JSON/Markdown pointer.
- Do not add external feed integrations; keep event-trigger maturity to the local file inbox unless a separate plan authorizes providers.

---

## Maturity Gates

FusionAgent can be renamed from "prototype" to "mature no-UI vector fusion agent" only when all gates pass:

1. **Research gate:** C1-C7 claims in `2026-04-20-evaluation-contract-claim-lock.md` have current evidence or explicit boundary text, and the final evidence freeze links every claim row to test, harness, or benchmark artifacts.
2. **Scenario autonomy gate:** at least one file-inbox trigger run proves event record normalization, idempotency, scenario creation, registry persistence, summary inspection, and evidence freeze.
3. **Runtime capability gate:** building, road, water, and bounded POI remain covered by the scenario regression manifest, with explicit execution-level versus planner-level capability semantics.
4. **Reproducibility gate:** official source-id materialization and AOI behavior are verified through tests plus at least one clean benchmark or documented deferred reason.
5. **Evidence product gate:** every curated run or scenario exposes machine-readable JSON and human-readable Markdown evidence.
6. **Operator API gate:** a no-UI operator can list, inspect, compare, and summarize runs/scenarios through APIs or CLI scripts without reading raw directories manually.
7. **Operations gate:** local fast mode, full-loop mode, trigger inbox, evidence freeze, cleanup, retention, and troubleshooting are documented as repeatable procedures.
8. **Positioning gate:** README and README.en stop calling the achieved core merely a prototype, while still marking final frontend, production deployment, and broad product concerns as not complete.

---

## File Map

Create:

- `docs/superpowers/specs/2026-04-21-no-ui-maturity-target.md`: exact claim boundary for "mature no-UI vector data fusion agent."
- `docs/superpowers/specs/2026-04-21-no-ui-maturity-gap-ledger.md`: reconciliation between README gaps, current evidence, and closure work.
- `docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.json`: machine-readable final maturity evidence package.
- `docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.md`: human-readable final maturity evidence summary.
- `docs/superpowers/specs/2026-04-21-operator-read-model-contract.md`: no-UI operator read-model contract for future UI consumption.
- `docs/superpowers/specs/2026-04-21-scenario-trigger-proof.md`: local file-inbox scenario-trigger proof.
- `docs/no-ui-agent-operations.md`: standalone no-UI operating runbook.
- `schemas/operator.py`: Pydantic response models for operator read APIs.
- `services/run_registry_service.py`: file-backed listing of persisted single-run records under `runs/`.
- `services/operator_read_model_service.py`: aggregate runtime, scenario, run, evidence, and artifact summaries into no-UI operator views.
- `services/artifact_preview_service.py`: produce artifact summaries and optional GeoJSON previews from zipped shapefile artifacts.
- `scripts/freeze_no_ui_maturity_evidence.py`: freeze final no-UI maturity evidence into JSON and Markdown.
- `scripts/run_no_ui_maturity_check.py`: run static and optional dynamic readiness checks for the no-UI maturity gate.
- `tests/test_run_registry_service.py`
- `tests/test_operator_read_model_service.py`
- `tests/test_artifact_preview_service.py`
- `tests/test_api_operator_read_models.py`
- `tests/test_freeze_no_ui_maturity_evidence.py`
- `tests/test_no_ui_maturity_check.py`

Modify:

- `api/routers/runs_v2.py`: add `GET /api/v2/runs` and `GET /api/v2/operator/summary` without changing existing run detail endpoints.
- `api/routers/scenario_runs.py`: keep existing scenario response contracts stable; only add operator-focused wrappers if needed.
- `schemas/agent.py`: add run list models only if they belong with existing run schemas; otherwise keep new models in `schemas/operator.py`.
- `services/scenario_registry_service.py`: harden ordering, duplicate lookup, and optional idempotency lookup.
- `services/scenario_run_service.py`: persist `idempotency_key` and source trigger metadata in scenario registry records when present.
- `scripts/watch_scenario_inbox.py`: add idempotency, failed-event handling, and JSON summary output.
- `docs/v2-operations.md`: add no-UI maturity operation path.
- `README.md` and `README.en.md`: update positioning only after all maturity gates pass.

---

## Task 1: Lock The No-UI Maturity Target

**Files:**
- Create: `docs/superpowers/specs/2026-04-21-no-ui-maturity-target.md`
- Create: `docs/superpowers/specs/2026-04-21-no-ui-maturity-gap-ledger.md`
- Modify: `docs/superpowers/specs/2026-04-20-evidence-ledger.md`

- [ ] **Step 1: Write the maturity target document**

Create `docs/superpowers/specs/2026-04-21-no-ui-maturity-target.md` with:

```markdown
# No-UI Maturity Target

## Target Statement

FusionAgent is considered a mature no-UI vector data fusion agent when it can accept natural-language and local scenario-triggered requests, select sources and workflows under KG/runtime constraints, execute or partially execute bounded building/road/water/POI tasks with explicit evidence semantics, recover through documented repair/replan paths, consume durable learning as bounded policy hints, produce auditable artifacts, and expose operator-grade read APIs and runbooks without requiring a final frontend.

## In Scope

- Natural-language task-driven requests.
- Local file-inbox scenario-triggered requests.
- KG-constrained planning and validation.
- Task-driven source acquisition for bounded official/local sources.
- Building, road, water, and bounded POI evidence with explicit execution-level versus planner-level status.
- Reactive healing, full replan V1 evidence, and bounded durable-learning policy hints.
- Machine-readable and human-readable evidence freeze artifacts.
- No-UI operator read APIs, CLI scripts, and runbooks.

## Out Of Scope

- Final visual frontend.
- Multi-user authentication.
- Production cloud deployment guarantees.
- External live event-feed provider integrations.
- Full policy auto-tuning.
- Arbitrary task-family extensibility.
- Live trajectory-to-road ingestion.

## Rename Gate

README wording may change from "prototype" to "mature no-UI vector data fusion agent" only after the maturity gates in `docs/superpowers/plans/2026-04-21-no-ui-mature-agent-plan.md` pass and the final evidence freeze is committed.
```

- [ ] **Step 2: Write the gap ledger**

Create `docs/superpowers/specs/2026-04-21-no-ui-maturity-gap-ledger.md` with a table mapping each README gap to closure action:

```markdown
# No-UI Maturity Gap Ledger

| README Gap | Current Status | Closure Action | Evidence Path | Required Before README Repositioning |
| --- | --- | --- | --- | --- |
| stronger robustness / learning / operator-facing claim still gated | C3/C4 are implemented, operator surface is thin | refresh evidence freeze and add operator read-model proof | `docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.md` | yes |
| search space remains bounded | building/road/water/bounded-POI are the stable claim | keep bounded wording and avoid arbitrary extensibility claims | `docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json` | yes |
| water/POI do not prove zero-cost new-topic expansion | planner/execution semantics differ by case | document partial semantics and capability tier | `docs/superpowers/specs/2026-04-21-no-ui-maturity-target.md` | yes |
| trajectory-to-road is reservation-only | no live runtime ingestion | keep as explicit boundary | README and maturity target | yes |
| durable learning is first-pass | bounded pattern-selection hint exists | freeze as bounded policy-hint evidence, not auto-tuning | paper and maturity freeze | yes |
| operator-facing productization is narrow API layer | inspection/compare/scenario APIs exist | add read models, run listing, no-UI runbook | operator tests and docs | yes |
| manual-only sources remain | some Google/reference/Excel paths remain manual | freeze supported official/local sources and document manual boundaries | source materialization tests and runbook | yes |
| AOI geocoder depends on network | Nominatim path exists with tests | add deterministic fixture/cache guidance or fallback test path | AOI tests and operations docs | yes |
```

- [ ] **Step 3: Update the evidence ledger**

Add a row under `Roadmap And Positioning Evidence`:

```markdown
| No-UI maturity target | `docs/superpowers/specs/2026-04-21-no-ui-maturity-target.md` | Defines the gate for calling FusionAgent a mature no-UI vector data fusion agent before frontend work | strong | Must stay synchronized with README positioning |
```

Add a row under `Missing Evidence To Create Next`:

```markdown
| No-UI maturity freeze | no-UI maturity plan | Final gate package before README can stop using prototype language for the achieved core |
```

- [ ] **Step 4: Verify documentation references**

Run:

```powershell
Select-String -Path docs/superpowers/specs/2026-04-21-no-ui-maturity-target.md -Pattern "mature no-UI vector data fusion agent"
Select-String -Path docs/superpowers/specs/2026-04-21-no-ui-maturity-gap-ledger.md -Pattern "operator-facing productization"
Select-String -Path docs/superpowers/specs/2026-04-20-evidence-ledger.md -Pattern "No-UI maturity target"
```

Expected: all three commands print at least one matching line.

Anti-pattern guards:

- Do not call the final frontend complete.
- Do not delete existing limitations; convert them into bounded closure gates.

---

## Task 2: Harden Scenario-Driven Autonomy Before UI

**Files:**
- Modify: `services/scenario_trigger_service.py`
- Modify: `scripts/watch_scenario_inbox.py`
- Modify: `services/scenario_registry_service.py`
- Modify: `services/scenario_run_service.py`
- Create: `docs/superpowers/specs/2026-04-21-scenario-trigger-proof.md`
- Test: `tests/test_scenario_trigger_service.py`

- [ ] **Step 1: Add failing tests for idempotent inbox behavior**

Extend `tests/test_scenario_trigger_service.py` with tests that prove `normalize_trigger_event()` preserves `metadata["idempotency_key"]`, `metadata["event_id"]`, and the location text in `trigger_content`.

Add a new test for invalid inbox events:

```python
def test_process_inbox_once_moves_invalid_events_to_failed_dir(tmp_path, monkeypatch) -> None:
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    failed = tmp_path / "failed"
    inbox.mkdir()
    (inbox / "bad.json").write_text("{not json", encoding="utf-8")

    processed_ids = process_inbox_once(inbox, processed, output_root=str(tmp_path / "out"), failed_dir=failed)

    assert processed_ids == []
    assert not (inbox / "bad.json").exists()
    assert (failed / "bad.json").exists()
```

- [ ] **Step 2: Run and confirm failure**

Run:

```powershell
python -m pytest -q tests/test_scenario_trigger_service.py
```

Expected: failure because `process_inbox_once()` does not yet accept `failed_dir`.

- [ ] **Step 3: Implement failed-event handling**

Change `process_inbox_once()` to accept `failed_dir: Optional[Path] = None`.

Behavior:

- valid JSON events are normalized and moved to `processed_dir`
- invalid JSON or runtime errors move the event file to `failed_dir` when provided
- if `failed_dir` is not provided, keep current fail-fast behavior
- printed CLI output remains JSON

- [ ] **Step 4: Add idempotency lookup before duplicate scenario creation**

Add `ScenarioRegistryService.find_by_idempotency_key(idempotency_key: str) -> Optional[Dict[str, Any]]`.

Wire `scripts/watch_scenario_inbox.py` so it checks the registry under the target scenario output root before creating a duplicate scenario. If a duplicate exists, move the file to `processed_dir` and return the existing `scenario_id`.

- [ ] **Step 5: Ensure scenario registry records include idempotency keys**

Modify the scenario registry record in `services/scenario_run_service.py` to include:

```python
"idempotency_key": request.metadata.get("idempotency_key"),
"trigger_event": request.metadata.get("trigger_event"),
```

Do not change the existing `ScenarioRunResponse`.

- [ ] **Step 6: Write trigger proof documentation**

Create `docs/superpowers/specs/2026-04-21-scenario-trigger-proof.md` with a sample event JSON, inbox command, processed/failed directory behavior, expected registry fields, expected scenario evidence files, and the limitation that this is local operations rather than external feed integration.

- [ ] **Step 7: Verify trigger path**

Run:

```powershell
python -m pytest -q tests/test_scenario_trigger_service.py tests/test_scenario_registry_service.py tests/test_api_scenario_registry.py
```

Expected: all tests pass.

Anti-pattern guards:

- Do not add a polling daemon or external provider integration.
- Do not make idempotency depend on process memory.
- Do not suppress failed-event evidence.

---

## Task 3: Add No-UI Operator Read Models

**Files:**
- Create: `schemas/operator.py`
- Create: `services/run_registry_service.py`
- Create: `services/operator_read_model_service.py`
- Modify: `api/routers/runs_v2.py`
- Test: `tests/test_run_registry_service.py`
- Test: `tests/test_operator_read_model_service.py`
- Test: `tests/test_api_operator_read_models.py`

- [ ] **Step 1: Write failing run registry tests**

Create `tests/test_run_registry_service.py`:

```python
from pathlib import Path

from services.run_registry_service import RunRegistryService


def test_run_registry_lists_persisted_run_json(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-a"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        '{"run_id":"run-a","phase":"succeeded","job_type":"building"}',
        encoding="utf-8",
    )

    records = RunRegistryService(runs_root=tmp_path / "runs").list_records(limit=10)

    assert records[0]["run_id"] == "run-a"
    assert records[0]["phase"] == "succeeded"
    assert records[0]["job_type"] == "building"
```

- [ ] **Step 2: Run and confirm failure**

Run:

```powershell
python -m pytest -q tests/test_run_registry_service.py
```

Expected: `ModuleNotFoundError: No module named 'services.run_registry_service'`.

- [ ] **Step 3: Implement `RunRegistryService`**

Create `services/run_registry_service.py` with a read-only service that scans `runs_root/*/run.json`, sorts by `run.json` modification time descending, supports `limit`, `phase`, and `job_type`, and adds `run_dir` to each returned record.

- [ ] **Step 4: Add operator schemas**

Create `schemas/operator.py` with:

```python
class OperatorRunListResponse(BaseModel):
    records: List[Dict[str, Any]] = Field(default_factory=list)


class OperatorRuntimeSummaryResponse(BaseModel):
    runtime: Dict[str, Any] = Field(default_factory=dict)
    recent_runs: List[Dict[str, Any]] = Field(default_factory=list)
    recent_scenarios: List[Dict[str, Any]] = Field(default_factory=list)
    evidence_gaps: List[str] = Field(default_factory=list)
```

Use Python 3.9-compatible imports from `typing`.

- [ ] **Step 5: Implement read model service**

Create `services/operator_read_model_service.py` with `OperatorReadModelService`.

`runtime_summary(limit=10)` must include:

- non-sensitive runtime env from `GEOFUSION_KG_BACKEND`, `GEOFUSION_LLM_PROVIDER`, `GEOFUSION_CELERY_EAGER`, `GEOFUSION_API_PORT`
- recent run records from `RunRegistryService`
- recent scenario records from `ScenarioRegistryService`
- `evidence_gaps` entries when no runs or scenarios are found

- [ ] **Step 6: Add API endpoints**

Modify `api/routers/runs_v2.py`:

```python
@router.get("/runs", response_model=OperatorRunListResponse)
async def list_runs(
    limit: int = Query(default=50, ge=1),
    phase: Optional[str] = None,
    job_type: Optional[str] = None,
) -> OperatorRunListResponse:
    records = RunRegistryService(runs_root=Path("runs")).list_records(
        limit=limit,
        phase=phase,
        job_type=job_type,
    )
    return OperatorRunListResponse(records=records)

@router.get("/operator/summary", response_model=OperatorRuntimeSummaryResponse)
async def get_operator_summary(limit: int = Query(default=10, ge=1)) -> OperatorRuntimeSummaryResponse:
    service = OperatorReadModelService(
        runs_root=Path("runs"),
        scenario_output_root=resolve_scenario_output_root(None),
    )
    return OperatorRuntimeSummaryResponse(**service.runtime_summary(limit=limit))
```

Use `RunRegistryService(runs_root=Path("runs"))` for the first implementation. Use `resolve_scenario_output_root(None)` for scenarios.

- [ ] **Step 7: Verify operator APIs**

Run:

```powershell
python -m pytest -q tests/test_run_registry_service.py tests/test_operator_read_model_service.py tests/test_api_operator_read_models.py tests/test_api_v2_integration.py
```

Expected: all tests pass.

Anti-pattern guards:

- Do not change existing `/api/v2/runs/{run_id}` behavior.
- Do not require raw directory reading by an operator for normal inspection.
- Do not include secrets or full `.env` values in runtime summary.

---

## Task 4: Add Artifact Preview And Evidence Products

**Files:**
- Create: `services/artifact_preview_service.py`
- Create: `tests/test_artifact_preview_service.py`
- Modify: `services/artifact_evaluation_service.py` only if shared helpers are needed
- Modify: `docs/v2-operations.md`

- [ ] **Step 1: Write failing artifact preview tests**

Create `tests/test_artifact_preview_service.py` using existing shapefile helper patterns from `tests/test_api_v2_integration.py` and assert:

```python
summary = build_artifact_preview(zip_path, output_dir=tmp_path / "preview")

assert summary["feature_count"] == 1
assert summary["bbox"] is not None
assert summary["geojson_path"].endswith(".geojson")
assert Path(summary["geojson_path"]).exists()
```

- [ ] **Step 2: Run and confirm failure**

Run:

```powershell
python -m pytest -q tests/test_artifact_preview_service.py
```

Expected: `ModuleNotFoundError: No module named 'services.artifact_preview_service'`.

- [ ] **Step 3: Implement `build_artifact_preview`**

Create `services/artifact_preview_service.py` with:

```python
def build_artifact_preview(artifact_zip: Path, *, output_dir: Path, max_features: int = 500) -> dict[str, Any]:
    return {
        "artifact_zip": str(artifact_zip),
        "output_dir": str(output_dir),
        "max_features": max_features,
    }
```

Behavior:

- safely extract the artifact zip to a temporary preview directory
- locate the first `.shp`
- load it with GeoPandas
- compute `feature_count`, `crs`, `geometry_types`, and WGS84 `bbox`
- write a capped `.geojson` preview under `output_dir`
- return paths and metrics as JSON-serializable values

- [ ] **Step 4: Add operations documentation**

Add to `docs/v2-operations.md`:

```markdown
### Artifact Preview Products

The no-UI maturity path can generate lightweight GeoJSON previews from artifact bundles before any final dashboard exists. These previews are operator and future-UI assets; they do not replace the canonical shapefile artifact bundle.
```

- [ ] **Step 5: Verify artifact preview**

Run:

```powershell
python -m pytest -q tests/test_artifact_preview_service.py tests/test_artifact_evaluation_service.py
```

Expected: all tests pass.

Anti-pattern guards:

- Do not replace shapefile bundles with GeoJSON as canonical artifacts.
- Do not attempt browser screenshots or UI thumbnails in this phase.
- Do not read arbitrary archive paths without safe extraction.

---

## Task 5: Strengthen Source Acquisition And AOI Reproducibility

**Files:**
- Modify: `services/aoi_resolution_service.py`
- Modify: `services/source_asset_service.py`
- Modify: `docs/v2-operations.md`
- Test: `tests/test_aoi_resolution_service.py`
- Test: `tests/test_source_asset_service.py`
- Test: `tests/test_raw_vector_source_service.py`

- [ ] **Step 1: Add deterministic AOI fixture guidance**

Do not replace `NominatimGeocoder`. Add documentation and tests for a deterministic fake geocoder path used by tests and maturity checks.

Extend `tests/test_aoi_resolution_service.py` with a fixture proving:

```python
service = AOIResolutionService(geocoder=FakeGeocoder([
    {
        "display_name": "Nairobi, Kenya",
        "boundingbox": ["-1.45", "-1.15", "36.65", "37.05"],
        "address": {"country": "Kenya", "country_code": "ke", "city": "Nairobi"},
        "importance": 0.91,
    }
]))
resolved = service.resolve("need building data for Nairobi, Kenya")
assert resolved.country_code == "ke"
assert resolved.selection_reason in {"single_candidate", "top_confidence_margin"}
```

- [ ] **Step 2: Verify current source materialization boundaries**

Run:

```powershell
python -m pytest -q tests/test_source_asset_service.py tests/test_raw_vector_source_service.py tests/test_local_bundle_catalog.py tests/test_input_acquisition_service.py
```

Expected: all tests pass.

- [ ] **Step 3: Write a source support table**

Add a table to `docs/v2-operations.md`:

```markdown
| Source ID | Local Data Supported | Remote Materialization Supported | Current Claim |
| --- | --- | --- | --- |
| raw.osm.building | yes | yes | mature no-UI supported |
| raw.osm.road | yes | yes | mature no-UI supported |
| raw.osm.water | yes | yes | planner-level scenario evidence unless execution source is available |
| raw.osm.poi | yes | yes | bounded POI evidence only |
| raw.microsoft.building | yes | yes | mature no-UI supported for bounded building |
| raw.google.building | yes | no | manual/local-only boundary |
```

- [ ] **Step 4: Decide whether to upgrade water/POI scenario claims**

Run the real scenario harness:

```powershell
python scripts/scenario_eval_harness.py `
  --manifest docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json `
  --base-url http://127.0.0.1:8000 `
  --output-root E:\fyx\data\fusionagentTEST `
  --output-json tmp/eval/scenario-harness-summary.json `
  --timeout 1200
```

If water and POI produce `task_inputs_resolved`, `source_coverage`, and at least one succeeded child in the current environment, update their manifest capability checks to execution-level.

If they remain planner-level, keep the existing manifest and add a clear note to the no-UI maturity target:

```text
Water and bounded POI are mature as bounded task-driven runtime slices, but the default fast-mode scenario regression set still treats them as planner-level capability checks when local raw source materialization is unavailable.
```

- [ ] **Step 5: Verify source and AOI path**

Run:

```powershell
python -m pytest -q tests/test_aoi_resolution_service.py tests/test_source_asset_service.py tests/test_raw_vector_source_service.py tests/test_input_acquisition_service.py tests/test_scenario_eval_harness.py
```

Expected: all tests pass.

Anti-pattern guards:

- Do not hide external geocoder dependency.
- Do not claim `raw.google.building` official auto-materialization unless it is implemented and tested.
- Do not force execution-level water/POI claims if the evidence remains planner-level in default verification.

---

## Task 6: Complete Research Evidence And Ablation Freeze

**Files:**
- Modify: `docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json`
- Modify: `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json`
- Modify: `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md`
- Modify: `scripts/freeze_paper_evidence.py` if new row types need formatting
- Test: `tests/test_freeze_paper_evidence.py`

- [ ] **Step 1: Add explicit scenario-driven evidence row**

Add a row to `2026-04-21-paper-experiment-matrix.json`:

```json
{
  "row_id": "c1_c2_c7_scenario_trigger_autonomy",
  "claim_ids": ["C1", "C2", "C7"],
  "baseline": "full_system",
  "dataset": "local file-inbox triggered disaster scenario",
  "summary_kind": "scenario_trigger_proof",
  "observed_status": "pending",
  "summary": "Local trigger event normalizes into a scenario run, persists registry evidence, and freezes scenario reports without manual API submission.",
  "evidence_paths": [
    "docs/superpowers/specs/2026-04-21-scenario-trigger-proof.md",
    "docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md"
  ],
  "supports_metrics": [
    "planning_validity_rate",
    "evidence_completeness_rate",
    "decision_trace_completeness"
  ]
}
```

Set `observed_status` to `passed` only after the trigger proof is actually executed and frozen.

- [ ] **Step 2: Add no-UI operator evidence row**

Add a row:

```json
{
  "row_id": "c8_no_ui_operator_surface",
  "claim_ids": ["C8-boundary"],
  "baseline": "operator_api_smoke",
  "dataset": "persisted run and scenario evidence",
  "summary_kind": "verification",
  "observed_status": "pending",
  "summary": "No-UI operator APIs expose run listing, scenario listing, runtime summary, inspection, and comparison without requiring a frontend.",
  "verification_command": [
    "python",
    "-m",
    "pytest",
    "-q",
    "tests/test_api_operator_read_models.py",
    "tests/test_api_v2_integration.py",
    "tests/test_api_scenario_registry.py"
  ],
  "verification_result": "pending",
  "supports_metrics": [
    "evidence_completeness_rate",
    "artifact_validity"
  ]
}
```

- [ ] **Step 3: Refresh paper evidence freeze**

Run:

```powershell
python scripts/freeze_paper_evidence.py `
  --spec docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json `
  --output-json docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json `
  --output-markdown docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md
```

Expected: updated JSON and Markdown include scenario trigger and no-UI operator rows.

- [ ] **Step 4: Verify freeze formatting**

Run:

```powershell
python -m pytest -q tests/test_freeze_paper_evidence.py
Select-String -Path docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md -Pattern "scenario_trigger_autonomy","no_ui_operator_surface"
```

Expected: tests pass and both rows appear in Markdown.

Anti-pattern guards:

- Do not mark pending rows as passed without executing their verification commands.
- Do not widen claims beyond C1-C8.
- Keep C8 as no-UI operator surface, not full frontend product.

---

## Task 7: Freeze No-UI Maturity Evidence

**Files:**
- Create: `scripts/freeze_no_ui_maturity_evidence.py`
- Create: `tests/test_freeze_no_ui_maturity_evidence.py`
- Create: `docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.json`
- Create: `docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.md`

- [ ] **Step 1: Write failing freeze test**

Create `tests/test_freeze_no_ui_maturity_evidence.py`:

```python
from pathlib import Path

from scripts.freeze_no_ui_maturity_evidence import freeze_no_ui_maturity_evidence


def test_freeze_no_ui_maturity_evidence_writes_json_and_markdown(tmp_path: Path) -> None:
    target = tmp_path / "target.md"
    target.write_text("# No-UI Maturity Target\n", encoding="utf-8")
    gap = tmp_path / "gap.md"
    gap.write_text("# No-UI Maturity Gap Ledger\n", encoding="utf-8")

    payload = freeze_no_ui_maturity_evidence(
        target_path=target,
        gap_ledger_path=gap,
        paper_evidence_path=tmp_path / "missing-paper.md",
        scenario_evidence_path=tmp_path / "missing-scenario.md",
        output_json=tmp_path / "freeze.json",
        output_markdown=tmp_path / "freeze.md",
    )

    assert payload["maturity_target_present"] is True
    assert payload["gap_ledger_present"] is True
    assert "maturity_target_present" in (tmp_path / "freeze.md").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run and confirm failure**

Run:

```powershell
python -m pytest -q tests/test_freeze_no_ui_maturity_evidence.py
```

Expected: import failure for `scripts.freeze_no_ui_maturity_evidence`.

- [ ] **Step 3: Implement freeze script**

Create `scripts/freeze_no_ui_maturity_evidence.py` with:

```python
def freeze_no_ui_maturity_evidence(
    *,
    target_path: Path,
    gap_ledger_path: Path,
    paper_evidence_path: Path,
    scenario_evidence_path: Path,
    output_json: Path,
    output_markdown: Path,
) -> dict[str, Any]:
    payload = {
        "maturity_target_present": target_path.exists(),
        "gap_ledger_present": gap_ledger_path.exists(),
        "paper_evidence_present": paper_evidence_path.exists(),
        "scenario_evidence_present": scenario_evidence_path.exists(),
        "gates": {},
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    output_markdown.write_text("# No-UI Maturity Evidence Freeze\n", encoding="utf-8")
    return payload
```

Required JSON fields:

- `maturity_target_present`
- `gap_ledger_present`
- `paper_evidence_present`
- `scenario_evidence_present`
- `gates`
- `generated_at`

Required Markdown sections:

- `# No-UI Maturity Evidence Freeze`
- `## Gate Status`
- `## Evidence Sources`
- `## Remaining Boundaries`

- [ ] **Step 4: Add CLI arguments**

Support:

```powershell
python scripts/freeze_no_ui_maturity_evidence.py `
  --target docs/superpowers/specs/2026-04-21-no-ui-maturity-target.md `
  --gap-ledger docs/superpowers/specs/2026-04-21-no-ui-maturity-gap-ledger.md `
  --paper-evidence docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md `
  --scenario-evidence docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md `
  --output-json docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.json `
  --output-markdown docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.md
```

- [ ] **Step 5: Verify maturity freeze**

Run:

```powershell
python -m pytest -q tests/test_freeze_no_ui_maturity_evidence.py
python scripts/freeze_no_ui_maturity_evidence.py `
  --target docs/superpowers/specs/2026-04-21-no-ui-maturity-target.md `
  --gap-ledger docs/superpowers/specs/2026-04-21-no-ui-maturity-gap-ledger.md `
  --paper-evidence docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md `
  --scenario-evidence docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md `
  --output-json docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.json `
  --output-markdown docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.md
```

Expected: test passes and both freeze files are written.

Anti-pattern guards:

- Do not compute maturity from untracked raw run directories alone.
- Do not omit remaining boundaries from the Markdown.

---

## Task 8: Write No-UI Operations Runbook

**Files:**
- Create: `docs/no-ui-agent-operations.md`
- Modify: `docs/v2-operations.md`
- Modify: `docs/demo/fusionagent-resume-project-brief.md`

- [ ] **Step 1: Create the no-UI runbook**

Create `docs/no-ui-agent-operations.md` with sections for purpose, fast runtime, full-loop runtime, scenario trigger inbox, scenario regression harness, real-data benchmark, evidence freeze, operator APIs, artifact preview, cleanup and retention, and known boundaries.

Include exact PowerShell commands from `docs/v2-operations.md` and this plan. Keep final UI explicitly out of scope.

- [ ] **Step 2: Add pointer from `docs/v2-operations.md`**

Add:

```markdown
For the consolidated no-UI maturity operating workflow, see [FusionAgent No-UI Operations](./no-ui-agent-operations.md).
```

- [ ] **Step 3: Update resume/demo brief**

Add one bullet under `What It Demonstrates`:

```markdown
- Mature no-UI operation through scenario triggers, operator read APIs, reproducible evidence freezes, and documented local runbooks before any final frontend is introduced.
```

- [ ] **Step 4: Verify docs**

Run:

```powershell
Select-String -Path docs/no-ui-agent-operations.md -Pattern "Scenario Trigger Inbox","Operator APIs","Known Boundaries"
Select-String -Path docs/v2-operations.md -Pattern "No-UI Operations"
Select-String -Path docs/demo/fusionagent-resume-project-brief.md -Pattern "Mature no-UI operation"
```

Expected: all commands print matching lines.

Anti-pattern guards:

- Do not duplicate every detail from `docs/v2-operations.md`; link to it where appropriate.
- Do not remove existing local fast/full-loop mode documentation.

---

## Task 9: Run The Final No-UI Maturity Check

**Files:**
- Create: `scripts/run_no_ui_maturity_check.py`
- Test: `tests/test_no_ui_maturity_check.py`

- [ ] **Step 1: Write failing maturity check test**

Create `tests/test_no_ui_maturity_check.py`:

```python
from pathlib import Path

from scripts.run_no_ui_maturity_check import collect_static_maturity_status


def test_collect_static_maturity_status_reports_required_docs(tmp_path: Path) -> None:
    required = tmp_path / "target.md"
    required.write_text("ok", encoding="utf-8")

    status = collect_static_maturity_status([required])

    assert status["required_files"][str(required)] is True
```

- [ ] **Step 2: Implement static maturity check**

Create `scripts/run_no_ui_maturity_check.py` with:

```python
def collect_static_maturity_status(required_files: list[Path]) -> dict[str, Any]:
    return {"required_files": {str(path): path.exists() for path in required_files}}
```

CLI behavior:

- checks required docs
- checks required freeze files
- checks that `README.md` and `README.en.md` contain no stale "prototype only" wording after repositioning
- optionally runs `python -m pytest -q` when `--run-tests` is provided
- exits `0` only if required static checks pass and optional tests pass

- [ ] **Step 3: Verify static check**

Run:

```powershell
python -m pytest -q tests/test_no_ui_maturity_check.py
python scripts/run_no_ui_maturity_check.py
```

Expected: test passes and script exits 0 once required docs exist.

Anti-pattern guards:

- Do not make this script start API servers.
- Do not make it depend on network access.
- Keep live runtime checks as documented commands, not implicit side effects.

---

## Task 10: Reposition README Only After Gates Pass

**Files:**
- Modify: `README.md`
- Modify: `README.en.md`
- Modify: `docs/superpowers/specs/2026-04-20-evidence-ledger.md`

- [ ] **Step 1: Confirm maturity gates**

Run:

```powershell
python scripts/run_no_ui_maturity_check.py
python -m pytest -q
```

Expected: static maturity checks and full suite pass.

- [ ] **Step 2: Update Chinese README positioning**

Replace the current status block with language equivalent to:

```markdown
- 工程 MVP：已达到
- 研究原型：已达到
- 无界面的成熟矢量数据融合智能体：已达到
- 最终可视化产品形态：尚未达到
```

Add:

```markdown
FusionAgent 当前可以作为无界面的成熟矢量数据融合智能体运行：它具备自然语言与本地场景触发入口、KG 约束规划、任务驱动数据获取、执行/修复/重规划/学习证据、场景级证据冻结、operator read API 与本地运维 runbook。最终可视化界面仍是后续 Phase H 工作。
```

- [ ] **Step 3: Update English README positioning**

Mirror the Chinese status:

```markdown
- Engineering MVP: reached
- Research prototype: reached
- Mature no-UI vector data fusion agent: reached
- Final visualization product shape: not reached
```

- [ ] **Step 4: Keep explicit boundaries**

Do not delete the current boundary list. Rewrite it so it says these are remaining product/frontier boundaries after no-UI maturity:

- final frontend is not built
- external provider event feeds are not integrated
- production deployment and auth are not claimed
- trajectory-to-road remains reservation-only
- arbitrary new task families are not claimed

- [ ] **Step 5: Verify README wording**

Run:

```powershell
Select-String -Path README.md -Pattern "无界面的成熟矢量数据融合智能体","最终可视化产品形态"
Select-String -Path README.en.md -Pattern "Mature no-UI vector data fusion agent","Final visualization product shape"
```

Expected: both commands print matching lines.

Anti-pattern guards:

- Do not imply a frontend exists.
- Do not remove limitations needed for paper honesty.
- Do not rename the project as production-ready.

---

## Final Verification

Run the focused new test set:

```powershell
python -m pytest -q `
  tests/test_scenario_trigger_service.py `
  tests/test_scenario_registry_service.py `
  tests/test_run_registry_service.py `
  tests/test_operator_read_model_service.py `
  tests/test_api_operator_read_models.py `
  tests/test_artifact_preview_service.py `
  tests/test_freeze_no_ui_maturity_evidence.py `
  tests/test_no_ui_maturity_check.py
```

Run the scenario and evidence set:

```powershell
python -m pytest -q `
  tests/test_scenario_manifest_service.py `
  tests/test_scenario_eval_harness.py `
  tests/test_freeze_scenario_evidence.py `
  tests/test_freeze_paper_evidence.py `
  tests/test_api_scenario_runs.py `
  tests/test_api_scenario_registry.py
```

Run the runtime and acquisition set:

```powershell
python -m pytest -q `
  tests/test_api_v2_integration.py `
  tests/test_agent_run_service_enhancements.py `
  tests/test_policy_engine.py `
  tests/test_aoi_resolution_service.py `
  tests/test_source_asset_service.py `
  tests/test_raw_vector_source_service.py `
  tests/test_input_acquisition_service.py `
  tests/test_artifact_evaluation_service.py
```

Run the full suite:

```powershell
python -m pytest -q
```

Run maturity static check:

```powershell
python scripts/run_no_ui_maturity_check.py
```

Run live scenario harness if local API is available:

```powershell
python scripts/scenario_eval_harness.py `
  --manifest docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json `
  --base-url http://127.0.0.1:8000 `
  --output-root E:\fyx\data\fusionagentTEST `
  --output-json tmp/eval/scenario-harness-summary.json `
  --timeout 1200
```

Refresh paper evidence:

```powershell
python scripts/freeze_paper_evidence.py `
  --spec docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json `
  --output-json docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json `
  --output-markdown docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md
```

Refresh no-UI maturity evidence:

```powershell
python scripts/freeze_no_ui_maturity_evidence.py `
  --target docs/superpowers/specs/2026-04-21-no-ui-maturity-target.md `
  --gap-ledger docs/superpowers/specs/2026-04-21-no-ui-maturity-gap-ledger.md `
  --paper-evidence docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md `
  --scenario-evidence docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md `
  --output-json docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.json `
  --output-markdown docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.md
```

Expected final status:

```text
all focused tests pass
full pytest suite passes
scenario harness has 0 failed cases or documented deferred live-run reason
paper evidence freeze exists
scenario evidence freeze exists
no-UI maturity evidence freeze exists
README and README.en reflect mature no-UI status while keeping final visualization out of scope
```

---

## Self-Review

- Spec coverage: This plan covers README explicit gaps, prior control-plane documents, scenario-trigger autonomy, research evidence freeze, source/AOI reproducibility, operator read APIs, artifact previews, no-UI operations, and final README repositioning.
- Scope control: The final UI, production auth, external event feeds, broad deployment, and trajectory-to-road runtime ingestion remain out of scope.
- Type consistency: New response models are isolated in `schemas/operator.py`; existing `schemas/scenario.py` and `schemas/agent.py` remain stable unless a narrow list response is needed.
- Evidence discipline: README repositioning is the final task and is gated on tests, evidence freeze, and maturity check output.
- Implementation risk: The highest-risk tasks are operator read models over persisted `runs/` and artifact preview extraction. Keep them read-only, file-backed, and covered by tests before connecting them to future UI work.
