# FusionAgent Targets 1,2,5,7-9 Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining engineering and evidence gaps for unattended operation, building height-raster auditability, bounded POI evidence, automatic source download, reporting, and automatic recovery without overstating the already-supported Targets 2-6 runtime.

**Architecture:** Keep the existing agent run pipeline intact and add narrow evidence services around it: one service for unattended runtime evidence, one service for source materialization manifests, and one service for report quality summaries. The implementation strengthens `task_driven_auto` scheduled execution, propagates source/download/quality evidence into audit events, reports, and inspection responses, and freezes the resulting capability boundary in checked-in evidence documents.

**Tech Stack:** Python 3.13 via `py -3.13`, FastAPI, Pydantic, Celery-compatible task wrappers, GeoPandas/Shapely/Rasterio/GDAL helpers already present in the repo, pytest, JSON/Markdown evidence artifacts.

---

## Scope And Claim Rules

The previous runtime closure states Targets 2-6 are supported. This plan does not reimplement vector conflation algorithms; it closes the remaining gap between "feature works in targeted runtime" and "agent can be operated, audited, reported, and recovered in a long-running unattended setting".

| Target | Current state | Gap to close in this plan | Claim after completion |
| --- | --- | --- | --- |
| 1 | API, local inbox, scheduled tick, and recovery tick exist | Scheduled tick is still upload-bundle oriented and long-running evidence is thin | Unattended local operation is supported with scheduled `task_driven_auto`, inbox evidence JSON, stale-run monitoring, and recovery evidence |
| 2 | Building vector fusion and optional height raster participation exist | Height raster participation is not prominent enough in report/evidence | Building fusion report explicitly records whether raster height participated, where the source came from, and what fields/metrics were affected |
| 5 | Bounded OSM + GNS/GeoNames POI fusion exists | Bounded support and unsupported unbounded alignment need stronger machine-readable evidence | Bounded POI fusion is auditable; unbounded POI entity alignment remains explicitly unsupported |
| 7 | `SourceAssetService` and `InputAcquisitionService` can download/cache/clip several sources | Download/cache/fault details are not preserved as a first-class materialization manifest | Automatic data download emits source materialization manifests, provider attempts, cache mode, version token, fault class, and clipping boundary |
| 8 | Run reports exist | Reports need a clearer quality/readiness summary for process and result assessment | Reports include process, result, data-source, quality-boundary, and paper-evidence readiness sections |
| 9 | Recovery scanner/executor exists | Recovery hints do not provide enough operator action text and classification evidence | Recovery hints, reports, and inspections expose recoverability, recovery action, operator action, failure category, and worker history |

Forbidden overclaims:

- Do not claim self-updating model weights, autonomous catalog mutation, or unsupervised policy rewriting. Target 10 remains "bounded policy hints and durable learning summaries only".
- Do not claim unbounded POI entity alignment. POI support remains AOI-bounded OSM + GNS/GeoNames vector fusion.
- Do not claim live download is guaranteed for every global source at all times. Network/provider availability remains provider-dependent; the system records attempts, cache reuse, and fault class.
- Do not claim Targets 2-6 are newly implemented here. This plan improves evidence and integration around those already-closed targets.

## File Structure Map

Create:

- `services/unattended_run_monitor_service.py`: Builds machine-readable unattended runtime snapshots from scheduled tick output, recovery tick output, inbox processing output, and recent run statuses.
- `tests/test_unattended_run_monitor_service.py`: Unit tests for unattended monitor snapshots and long-running readiness classification.
- `services/source_materialization_manifest_service.py`: Converts automatic input/source resolution events into `source_materialization_manifest.json` payloads with provider attempts, source mode, cache hit, version token, clipping/aoi evidence, and fault classification.
- `tests/test_source_materialization_manifest_service.py`: Unit tests for manifest shape for downloaded, cache-reused, clipped, and failed provider cases.
- `services/report_quality_service.py`: Builds report quality summaries for Targets 1,2,5,7,8,9 from run status, audit events, semantic contract, artifact metrics, and recovery evidence.
- `tests/test_report_quality_service.py`: Unit tests for height raster auditability, bounded POI evidence, source download evidence, and report readiness scores.
- `docs/superpowers/specs/2026-05-29-targets-1-2-5-7-9-gap-closure-evidence.md`: Human-readable evidence freeze.
- `docs/superpowers/specs/2026-05-29-targets-1-2-5-7-9-gap-closure-evidence.json`: Machine-readable evidence freeze used by guard tests.
- `tests/test_targets_1_2_5_7_9_gap_closure_evidence.py`: Guard tests that the evidence freeze and research summary do not overclaim.

Modify:

- `worker/tasks.py`: Allow scheduled specs with `input_strategy="task_driven_auto"` and no uploaded zip paths; return per-spec input mode and error summaries.
- `tests/test_worker_orchestration.py`: Add scheduled tick coverage for `task_driven_auto` specs.
- `scripts/watch_scenario_inbox.py`: Add `--evidence-json` and persist processed/failed/idempotent counts.
- `tests/test_watch_scenario_inbox.py`: Add evidence JSON coverage for processed and failed events.
- `services/input_acquisition_service.py`: Persist a materialization manifest beside cached input bundles and expose `manifest_path` in `ResolvedRunInputs`.
- `tests/test_input_acquisition_service.py`: Assert manifests are written for downloaded and clipped reused bundles.
- `services/agent_run_service.py`: Include `source_materialization_manifest_path` in `task_inputs_resolved`, load it into run reports, and keep large-area runtime behavior unchanged.
- `services/run_report_service.py`: Add `quality_summary` and `evidence_readiness` to JSON/Markdown reports.
- `tests/test_run_report_service.py`: Assert reports render quality summary, height raster participation, bounded POI boundary, and recovery action.
- `services/run_recovery_service.py`: Add `operator_action` and `classification_evidence` to `build_recovery_hint()`.
- `tests/test_run_recovery_service.py`: Assert recoverable and manual-review hints include operator actions.
- `api/routers/runs_v2.py`: Expose report quality summary from `run_report_summary.json` in `/api/v2/runs/{run_id}/inspection`.
- `schemas/agent.py`: Extend `RunInspectionResponse` with `report_quality_summary` and `evidence_readiness`.
- `tests/test_api_v2_integration.py` or a focused API test: Assert inspection includes report quality fields from saved report summary.
- `文档/研究总结0529.md`: Append a short "0529 gap closure plan" section aligning the research material with this capability boundary.

## Implementation Tasks

### Task 1: Strengthen Unattended Runtime Evidence

**Files:**
- Create: `services/unattended_run_monitor_service.py`
- Create: `tests/test_unattended_run_monitor_service.py`
- Modify: `worker/tasks.py`
- Modify: `tests/test_worker_orchestration.py`
- Modify: `scripts/watch_scenario_inbox.py`
- Test: `tests/test_unattended_run_monitor_service.py`, `tests/test_worker_orchestration.py`, inbox script test file

- [ ] **Step 1: Write failing monitor service tests**

Create `tests/test_unattended_run_monitor_service.py`:

```python
from __future__ import annotations

from services.unattended_run_monitor_service import (
    build_unattended_runtime_snapshot,
    classify_unattended_readiness,
)


def test_classify_unattended_readiness_ready_when_schedule_inbox_and_recovery_have_evidence() -> None:
    snapshot = build_unattended_runtime_snapshot(
        scheduled_tick_result={
            "configured": 2,
            "created": 2,
            "run_ids": ["run-a", "run-b"],
            "errors": [],
            "spec_results": [
                {"index": 1, "status": "created", "input_strategy": "task_driven_auto", "run_id": "run-a"},
                {"index": 2, "status": "created", "input_strategy": "uploaded", "run_id": "run-b"},
            ],
        },
        inbox_result={"processed": ["scenario-a"], "failed": [], "idempotent": []},
        recovery_tick_result={"enabled": True, "attempted": 1, "recovered": 1, "failed": 0, "records": []},
        recent_runs=[
            {"run_id": "run-a", "phase": "succeeded"},
            {"run_id": "run-b", "phase": "succeeded"},
        ],
    )

    assert snapshot["readiness"] == "ready"
    assert snapshot["unattended_modes"]["scheduled_task_driven_auto"] is True
    assert snapshot["unattended_modes"]["local_inbox"] is True
    assert snapshot["unattended_modes"]["recovery_tick"] is True
    assert snapshot["manual_intervention_required"] is False
    assert snapshot["long_running_boundary"] == "process supervision and external scheduler uptime are environment responsibilities"


def test_classify_unattended_readiness_degraded_when_recovery_disabled_or_errors_present() -> None:
    readiness = classify_unattended_readiness(
        scheduled_errors=["scheduled_spec_1: ValueError: bad source"],
        inbox_failed_count=1,
        recovery_enabled=False,
        recovery_failed_count=0,
    )

    assert readiness == "degraded"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
py -3.13 -m pytest -q tests/test_unattended_run_monitor_service.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'services.unattended_run_monitor_service'`.

- [ ] **Step 3: Implement the monitor service**

Create `services/unattended_run_monitor_service.py`:

```python
from __future__ import annotations

from typing import Any


def classify_unattended_readiness(
    *,
    scheduled_errors: list[str],
    inbox_failed_count: int,
    recovery_enabled: bool,
    recovery_failed_count: int,
) -> str:
    if scheduled_errors or inbox_failed_count > 0 or recovery_failed_count > 0:
        return "degraded"
    if not recovery_enabled:
        return "degraded"
    return "ready"


def build_unattended_runtime_snapshot(
    *,
    scheduled_tick_result: dict[str, Any],
    inbox_result: dict[str, Any] | None,
    recovery_tick_result: dict[str, Any],
    recent_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    spec_results = [
        item for item in scheduled_tick_result.get("spec_results", [])
        if isinstance(item, dict)
    ]
    scheduled_errors = [str(item) for item in scheduled_tick_result.get("errors", [])]
    inbox_payload = inbox_result or {}
    inbox_failed = inbox_payload.get("failed", [])
    recovery_enabled = bool(recovery_tick_result.get("enabled", False))
    recovery_failed_count = int(recovery_tick_result.get("failed", 0) or 0)
    readiness = classify_unattended_readiness(
        scheduled_errors=scheduled_errors,
        inbox_failed_count=len(inbox_failed) if isinstance(inbox_failed, list) else 0,
        recovery_enabled=recovery_enabled,
        recovery_failed_count=recovery_failed_count,
    )
    return {
        "readiness": readiness,
        "manual_intervention_required": readiness != "ready",
        "unattended_modes": {
            "scheduled": int(scheduled_tick_result.get("configured", 0) or 0) > 0,
            "scheduled_task_driven_auto": any(
                item.get("status") == "created" and item.get("input_strategy") == "task_driven_auto"
                for item in spec_results
            ),
            "local_inbox": bool(inbox_payload.get("processed")),
            "recovery_tick": recovery_enabled,
        },
        "scheduled_tick": scheduled_tick_result,
        "inbox": inbox_payload,
        "recovery_tick": recovery_tick_result,
        "recent_runs": recent_runs,
        "long_running_boundary": "process supervision and external scheduler uptime are environment responsibilities",
    }
```

- [ ] **Step 4: Run monitor tests**

Run:

```powershell
py -3.13 -m pytest -q tests/test_unattended_run_monitor_service.py
```

Expected: PASS.

- [ ] **Step 5: Write failing scheduled `task_driven_auto` test**

Append to `tests/test_worker_orchestration.py`:

```python
def test_scheduled_tick_creates_task_driven_auto_run_without_uploaded_bundles(monkeypatch) -> None:
    scheduled_runs = [
        {
            "job_type": "poi",
            "trigger_content": "nightly bounded poi refresh",
            "spatial_extent": "bbox(36.7,-1.3,36.9,-1.1)",
            "target_crs": "EPSG:4326",
            "input_strategy": "task_driven_auto",
            "preferred_pattern_id": "wp.generic.poi.default",
        }
    ]
    monkeypatch.setenv("GEOFUSION_SCHEDULED_RUNS", json.dumps(scheduled_runs))

    worker_tasks = importlib.import_module("worker.tasks")
    service_module = importlib.import_module("services.agent_run_service")

    calls: list[RunCreateRequest] = []

    class StubService:
        def create_run(
            self,
            request: RunCreateRequest,
            osm_zip_name: str | None,
            osm_zip_bytes: bytes | None,
            ref_zip_name: str | None,
            ref_zip_bytes: bytes | None,
        ):
            calls.append(request)
            assert osm_zip_name is None
            assert osm_zip_bytes is None
            assert ref_zip_name is None
            assert ref_zip_bytes is None
            return type("CreatedRun", (), {"run_id": "run-auto"})()

    monkeypatch.setattr(service_module, "agent_run_service", StubService())

    result = worker_tasks.scheduled_tick()

    assert result["created"] == 1
    assert result["run_ids"] == ["run-auto"]
    assert result["spec_results"] == [
        {"index": 1, "status": "created", "run_id": "run-auto", "input_strategy": "task_driven_auto"}
    ]
    assert calls[0].input_strategy == RunInputStrategy.task_driven_auto
    assert calls[0].preferred_pattern_id == "wp.generic.poi.default"
```

- [ ] **Step 6: Run scheduled test to verify it fails**

Run:

```powershell
py -3.13 -m pytest -q tests/test_worker_orchestration.py::test_scheduled_tick_creates_task_driven_auto_run_without_uploaded_bundles
```

Expected: FAIL with `KeyError: 'osm_zip_path'` or missing `spec_results`.

- [ ] **Step 7: Implement scheduled `task_driven_auto` support**

Modify imports in `worker/tasks.py`:

```python
from schemas.agent import RepairRecord, RunCreateRequest, RunInputStrategy, RunTrigger, RunTriggerType, WorkflowPlan
```

Replace the body of `scheduled_tick()` with:

```python
@celery_app.task(name="geofusion.scheduled_tick")
def scheduled_tick() -> Dict[str, Any]:
    from services.agent_run_service import agent_run_service

    run_ids: List[str] = []
    errors: List[str] = []
    spec_results: List[Dict[str, Any]] = []
    scheduled_specs = _load_scheduled_specs()
    for index, spec in enumerate(scheduled_specs, start=1):
        if spec.get("enabled", True) is False:
            spec_results.append({"index": index, "status": "skipped_disabled"})
            continue
        input_strategy = RunInputStrategy(str(spec.get("input_strategy", RunInputStrategy.uploaded.value)))
        try:
            request = RunCreateRequest(
                job_type=JobType(spec["job_type"]),
                trigger=RunTrigger(
                    type=RunTriggerType.scheduled,
                    content=str(spec.get("trigger_content", f"scheduled-{index}")),
                    disaster_type=spec.get("disaster_type"),
                    spatial_extent=spec.get("spatial_extent"),
                    temporal_start=spec.get("temporal_start"),
                    temporal_end=spec.get("temporal_end"),
                ),
                target_crs=str(spec.get("target_crs", "EPSG:32643")),
                field_mapping=dict(spec.get("field_mapping", {})),
                debug=bool(spec.get("debug", False)),
                input_strategy=input_strategy,
                preferred_pattern_id=spec.get("preferred_pattern_id"),
            )
            if input_strategy == RunInputStrategy.uploaded:
                osm_zip_path = Path(str(spec["osm_zip_path"]))
                ref_zip_path = Path(str(spec["ref_zip_path"]))
                created = agent_run_service.create_run(
                    request=request,
                    osm_zip_name=osm_zip_path.name,
                    osm_zip_bytes=osm_zip_path.read_bytes(),
                    ref_zip_name=ref_zip_path.name,
                    ref_zip_bytes=ref_zip_path.read_bytes(),
                )
            else:
                created = agent_run_service.create_run(
                    request=request,
                    osm_zip_name=None,
                    osm_zip_bytes=None,
                    ref_zip_name=None,
                    ref_zip_bytes=None,
                )
            run_ids.append(created.run_id)
            spec_results.append(
                {
                    "index": index,
                    "status": "created",
                    "run_id": created.run_id,
                    "input_strategy": input_strategy.value,
                }
            )
        except Exception as exc:  # noqa: BLE001
            message = f"scheduled_spec_{index}: {type(exc).__name__}: {exc}"
            LOGGER.warning(message)
            errors.append(message)
            spec_results.append(
                {
                    "index": index,
                    "status": "error",
                    "input_strategy": str(spec.get("input_strategy", RunInputStrategy.uploaded.value)),
                    "error": message,
                }
            )

    return {
        "configured": len(scheduled_specs),
        "created": len(run_ids),
        "run_ids": run_ids,
        "errors": errors,
        "spec_results": spec_results,
    }
```

- [ ] **Step 8: Run scheduled tests**

Run:

```powershell
py -3.13 -m pytest -q tests/test_worker_orchestration.py::test_scheduled_tick_creates_runs_from_config tests/test_worker_orchestration.py::test_scheduled_tick_creates_task_driven_auto_run_without_uploaded_bundles tests/test_worker_orchestration.py::test_scheduled_tick_control_state_reports_configured_specs
```

Expected: PASS.

- [ ] **Step 9: Write failing inbox evidence JSON test**

Create `tests/test_watch_scenario_inbox.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from scripts.watch_scenario_inbox import process_inbox_once


def test_process_inbox_once_writes_evidence_json_for_processed_and_failed_events(tmp_path: Path, monkeypatch) -> None:
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    failed = tmp_path / "failed"
    evidence = tmp_path / "inbox_evidence.json"
    inbox.mkdir()
    (inbox / "good.json").write_text(
        json.dumps(
            {
                "event_id": "evt-good",
                "scenario_name": "nightly scenario",
                "disaster_type": "flood",
                "job_types": ["building"],
                "spatial_extent": "bbox(0,0,1,1)",
            }
        ),
        encoding="utf-8",
    )
    (inbox / "bad.json").write_text("{bad json", encoding="utf-8")

    import scripts.watch_scenario_inbox as module

    monkeypatch.setattr(
        module.scenario_run_service,
        "create_scenario_run",
        lambda request: type("Response", (), {"scenario_id": "scenario-good"})(),
    )

    processed_ids = process_inbox_once(
        inbox,
        processed,
        failed_dir=failed,
        evidence_json=evidence,
    )

    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert processed_ids == ["scenario-good"]
    assert payload["processed"] == ["scenario-good"]
    assert payload["failed"] == [{"filename": "bad.json", "error_type": "JSONDecodeError"}]
    assert payload["counts"] == {"processed": 1, "failed": 1, "idempotent": 0}
```

- [ ] **Step 10: Run inbox evidence test to verify it fails**

Run:

```powershell
py -3.13 -m pytest -q tests/test_watch_scenario_inbox.py::test_process_inbox_once_writes_evidence_json_for_processed_and_failed_events
```

Expected: FAIL with `TypeError: process_inbox_once() got an unexpected keyword argument 'evidence_json'`.

- [ ] **Step 11: Implement inbox evidence JSON**

Modify signature in `scripts/watch_scenario_inbox.py`:

```python
def process_inbox_once(
    inbox_dir: Path,
    processed_dir: Path,
    output_root: Optional[str] = None,
    failed_dir: Optional[Path] = None,
    evidence_json: Optional[Path] = None,
) -> list[str]:
```

Inside the function, initialize before the loop:

```python
    failed_records: list[dict[str, str]] = []
    idempotent_ids: list[str] = []
```

In the idempotent branch, before `scenario_ids.append(...)`:

```python
                idempotent_ids.append(str(existing["scenario_id"]))
```

Change the `except Exception:` block to:

```python
        except Exception as exc:
            if failed_path is None:
                raise
            failed_records.append({"filename": event_path.name, "error_type": type(exc).__name__})
            _move_event_file(event_path, failed_path)
```

Before returning:

```python
    if evidence_json is not None:
        evidence_path = Path(evidence_json)
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            json.dumps(
                {
                    "processed": scenario_ids,
                    "failed": failed_records,
                    "idempotent": idempotent_ids,
                    "counts": {
                        "processed": len(scenario_ids),
                        "failed": len(failed_records),
                        "idempotent": len(idempotent_ids),
                    },
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
```

Add CLI argument:

```python
    parser.add_argument("--evidence-json", default=None, help="Optional JSON path for inbox processing evidence.")
```

Pass it in `main()`:

```python
        evidence_json=Path(args.evidence_json) if args.evidence_json is not None else None,
```

- [ ] **Step 12: Run Task 1 tests**

Run:

```powershell
py -3.13 -m pytest -q tests/test_unattended_run_monitor_service.py tests/test_worker_orchestration.py tests/test_watch_scenario_inbox.py
```

Expected: PASS.

- [ ] **Step 13: Commit Task 1**

```powershell
git add services/unattended_run_monitor_service.py tests/test_unattended_run_monitor_service.py worker/tasks.py tests/test_worker_orchestration.py scripts/watch_scenario_inbox.py tests/test_watch_scenario_inbox.py
git commit -m "feat: strengthen unattended runtime evidence"
```

### Task 2: Make Building Height Raster Participation Auditable

**Files:**
- Create: `services/report_quality_service.py`
- Create: `tests/test_report_quality_service.py`
- Modify: `services/run_report_service.py`
- Modify: `tests/test_run_report_service.py`

- [ ] **Step 1: Write failing quality service tests for height raster evidence**

Create `tests/test_report_quality_service.py`:

```python
from __future__ import annotations

from schemas.agent import RunEvent, RunPhase
from schemas.fusion import JobType
from services.report_quality_service import build_report_quality_summary


def test_report_quality_summary_marks_height_raster_participation() -> None:
    summary = build_report_quality_summary(
        job_type=JobType.building.value,
        audit_events=[
            RunEvent(
                timestamp="2026-05-29T00:00:00+00:00",
                kind="task_inputs_resolved",
                phase=RunPhase.running,
                message="inputs",
                details={
                    "component_coverage": {
                        "raw.osm.building": {"feature_count": 2},
                        "raw.google.building_height.raster": {"path": "height.tif", "raster_profile": {"bands": 1}},
                    }
                },
            )
        ],
        source_semantic_contract={
            "height_policy": {
                "raster_height_sources": {"raw.google.building_height.raster": "height.tif"},
                "height_fields": ["height"],
            }
        },
        artifact_metrics={"artifact_validity": True, "feature_count": 2},
        recovery_evidence={},
    )

    assert summary["target_capability"]["target_2_building_height_raster"]["supported"] is True
    assert summary["target_capability"]["target_2_building_height_raster"]["raster_participated"] is True
    assert summary["target_capability"]["target_2_building_height_raster"]["source_ids"] == [
        "raw.google.building_height.raster"
    ]
    assert summary["evidence_readiness_score"] >= 0.8
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
py -3.13 -m pytest -q tests/test_report_quality_service.py::test_report_quality_summary_marks_height_raster_participation
```

Expected: FAIL with `ModuleNotFoundError: No module named 'services.report_quality_service'`.

- [ ] **Step 3: Implement height raster quality summary**

Create `services/report_quality_service.py`:

```python
from __future__ import annotations

from typing import Any

from schemas.agent import RunEvent


def build_report_quality_summary(
    *,
    job_type: str,
    audit_events: list[RunEvent],
    source_semantic_contract: dict[str, Any] | None,
    artifact_metrics: dict[str, Any],
    recovery_evidence: dict[str, Any] | None,
) -> dict[str, Any]:
    contract = source_semantic_contract or {}
    recovery = recovery_evidence or {}
    height_sources = _height_raster_source_ids(contract=contract, audit_events=audit_events)
    source_download = _source_download_summary(audit_events)
    poi_boundary = _poi_boundary_summary(job_type=job_type, audit_events=audit_events, contract=contract)
    recovery_summary = _recovery_summary(recovery)
    checks = [
        bool(artifact_metrics.get("artifact_validity")),
        bool(source_download["has_task_inputs_resolved"]),
        bool(height_sources) if job_type == "building" else True,
        poi_boundary["bounded"] if job_type == "poi" else True,
        recovery_summary["operator_action_available"] or not recovery_summary["recoverable"],
    ]
    score = sum(1 for item in checks if item) / len(checks)
    return {
        "evidence_readiness_score": round(score, 3),
        "target_capability": {
            "target_1_unattended": {"supported": source_download["has_task_inputs_resolved"]},
            "target_2_building_height_raster": {
                "supported": job_type == "building",
                "raster_participated": bool(height_sources),
                "source_ids": height_sources,
            },
            "target_5_bounded_poi": poi_boundary,
            "target_7_auto_download": source_download,
            "target_8_report": {"supported": True, "sections": ["process", "result", "quality", "boundary"]},
            "target_9_recovery": recovery_summary,
        },
        "quality_boundary": {
            "poi": "bounded AOI OSM + GNS/GeoNames fusion; unbounded POI entity alignment is unsupported",
            "self_evolution": "bounded policy hints only; no automatic model, policy, or source catalog mutation",
            "download": "provider availability is external; manifests record cache, retry, and fault evidence",
        },
    }


def _height_raster_source_ids(*, contract: dict[str, Any], audit_events: list[RunEvent]) -> list[str]:
    source_ids: set[str] = set()
    height_policy = contract.get("height_policy")
    if isinstance(height_policy, dict):
        raster_sources = height_policy.get("raster_height_sources")
        if isinstance(raster_sources, dict):
            source_ids.update(str(key) for key in raster_sources if key)
    for event in audit_events:
        coverage = event.details.get("component_coverage") if event.kind == "task_inputs_resolved" else None
        if isinstance(coverage, dict):
            for source_id, payload in coverage.items():
                if "raster" in str(source_id) or "height" in str(source_id):
                    if isinstance(payload, dict) and (payload.get("path") or payload.get("raster_profile")):
                        source_ids.add(str(source_id))
    return sorted(source_ids)


def _source_download_summary(audit_events: list[RunEvent]) -> dict[str, Any]:
    resolved = [event for event in audit_events if event.kind == "task_inputs_resolved"]
    modes = sorted(
        {
            str(event.details.get("source_mode"))
            for event in resolved
            if event.details.get("source_mode") is not None
        }
    )
    manifest_paths = [
        str(event.details.get("source_materialization_manifest_path"))
        for event in resolved
        if event.details.get("source_materialization_manifest_path")
    ]
    return {
        "supported": bool(resolved),
        "has_task_inputs_resolved": bool(resolved),
        "source_modes": modes,
        "manifest_paths": manifest_paths,
        "cache_hit_observed": any(bool(event.details.get("cache_hit")) for event in resolved),
    }


def _poi_boundary_summary(*, job_type: str, audit_events: list[RunEvent], contract: dict[str, Any]) -> dict[str, Any]:
    source_ids: set[str] = set()
    for event in audit_events:
        coverage = event.details.get("component_coverage") if event.kind == "task_inputs_resolved" else None
        if isinstance(coverage, dict):
            source_ids.update(str(key) for key in coverage)
    component_ids = contract.get("component_source_ids")
    if isinstance(component_ids, list):
        source_ids.update(str(item) for item in component_ids)
    bounded = job_type != "poi" or {"raw.osm.poi", "raw.gns.poi"}.issubset(source_ids)
    return {
        "supported": job_type == "poi",
        "bounded": bounded,
        "source_ids": sorted(source_ids),
        "unsupported_boundary": "unbounded POI entity alignment is unsupported",
    }


def _recovery_summary(recovery: dict[str, Any]) -> dict[str, Any]:
    recoverable = bool(recovery.get("recoverable", False))
    operator_action = str(recovery.get("operator_action") or "").strip()
    return {
        "supported": True,
        "recoverable": recoverable,
        "recovery_action": recovery.get("recovery_action", "none"),
        "operator_action_available": bool(operator_action),
        "operator_action": operator_action or None,
        "failure_category": recovery.get("failure_category"),
    }
```

- [ ] **Step 4: Run quality service test**

Run:

```powershell
py -3.13 -m pytest -q tests/test_report_quality_service.py::test_report_quality_summary_marks_height_raster_participation
```

Expected: PASS.

- [ ] **Step 5: Write failing run report test for quality summary**

Append to `tests/test_run_report_service.py`:

```python
def test_run_report_includes_quality_summary_for_height_raster(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.gpkg"
    artifact.write_bytes(b"gpkg")
    status = _run_status(artifact)

    summary = build_run_report_summary(
        status=status,
        plan=_plan(),
        audit_events=_audit_events(),
        artifact_path=artifact,
        source_semantic_contract={
            "height_policy": {
                "raster_height_sources": {"raw.google.building_height.raster": "height.tif"},
                "height_fields": ["height"],
            }
        },
    )

    assert summary["quality_summary"]["target_capability"]["target_2_building_height_raster"] == {
        "supported": True,
        "raster_participated": True,
        "source_ids": ["raw.google.building_height.raster"],
    }
    assert summary["evidence_readiness"]["score"] == summary["quality_summary"]["evidence_readiness_score"]
```

- [ ] **Step 6: Run run report test to verify it fails**

Run:

```powershell
py -3.13 -m pytest -q tests/test_run_report_service.py::test_run_report_includes_quality_summary_for_height_raster
```

Expected: FAIL with `KeyError: 'quality_summary'`.

- [ ] **Step 7: Integrate quality summary into reports**

Modify `services/run_report_service.py` imports:

```python
from services.report_quality_service import build_report_quality_summary
```

Inside `build_run_report_summary()`, create `artifact_metrics` before `summary = { ... }`:

```python
    artifact_metrics = _artifact_metrics(status=status, artifact_path=artifact_path)
    recovery_hint = build_recovery_hint(status.model_dump(mode="json"))
    quality_summary = build_report_quality_summary(
        job_type=status.job_type.value,
        audit_events=audit_events,
        source_semantic_contract=source_semantic_contract or {},
        artifact_metrics=artifact_metrics,
        recovery_evidence=recovery_hint,
    )
```

Use `artifact_metrics` in the existing `evaluation.result.artifact_metrics` field. Replace the inline `build_recovery_hint(...)` call with `recovery_hint`. Add top-level fields:

```python
        "quality_summary": quality_summary,
        "evidence_readiness": {
            "score": quality_summary["evidence_readiness_score"],
            "boundary": quality_summary["quality_boundary"],
        },
```

In `_render_zh(summary)`, add after result evaluation:

```python
            "## 质量与证据边界",
            f"- {_compact(summary.get('quality_summary', {}))}",
```

In `_render_en(summary)`, add after result evaluation:

```python
            "## Quality And Evidence Boundary",
            f"- {_compact(summary.get('quality_summary', {}))}",
```

- [ ] **Step 8: Run Task 2 tests**

Run:

```powershell
py -3.13 -m pytest -q tests/test_report_quality_service.py tests/test_run_report_service.py
```

Expected: PASS.

- [ ] **Step 9: Commit Task 2**

```powershell
git add services/report_quality_service.py tests/test_report_quality_service.py services/run_report_service.py tests/test_run_report_service.py
git commit -m "feat: add run report quality evidence"
```

### Task 3: Strengthen Bounded POI Evidence And Guards

**Files:**
- Modify: `tests/test_report_quality_service.py`
- Modify: `tests/test_run_report_service.py`
- Modify: `services/report_quality_service.py`
- Modify: `docs/superpowers/specs/2026-05-28-targets-2-6-runtime-evidence-freeze.md`

- [ ] **Step 1: Write failing bounded POI quality test**

Append to `tests/test_report_quality_service.py`:

```python
def test_report_quality_summary_marks_bounded_poi_and_rejects_unbounded_claim() -> None:
    summary = build_report_quality_summary(
        job_type=JobType.poi.value,
        audit_events=[
            RunEvent(
                timestamp="2026-05-29T00:00:00+00:00",
                kind="task_inputs_resolved",
                phase=RunPhase.running,
                message="poi inputs",
                details={
                    "resolved_aoi": {
                        "display_name": "Nairobi, Kenya",
                        "bbox": [36.65, -1.45, 37.10, -1.10],
                    },
                    "component_coverage": {
                        "raw.osm.poi": {"feature_count": 5},
                        "raw.gns.poi": {"feature_count": 2},
                    },
                },
            )
        ],
        source_semantic_contract={"component_source_ids": ["raw.osm.poi", "raw.gns.poi"]},
        artifact_metrics={"artifact_validity": True, "feature_count": 7},
        recovery_evidence={},
    )

    poi = summary["target_capability"]["target_5_bounded_poi"]
    assert poi["supported"] is True
    assert poi["bounded"] is True
    assert poi["aoi_bound"] == [36.65, -1.45, 37.10, -1.10]
    assert poi["source_ids"] == ["raw.gns.poi", "raw.osm.poi"]
    assert poi["unsupported_boundary"] == "unbounded POI entity alignment is unsupported"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
py -3.13 -m pytest -q tests/test_report_quality_service.py::test_report_quality_summary_marks_bounded_poi_and_rejects_unbounded_claim
```

Expected: FAIL with `KeyError: 'aoi_bound'`.

- [ ] **Step 3: Implement AOI-bound extraction for POI**

Replace `_poi_boundary_summary()` in `services/report_quality_service.py` with:

```python
def _poi_boundary_summary(*, job_type: str, audit_events: list[RunEvent], contract: dict[str, Any]) -> dict[str, Any]:
    source_ids: set[str] = set()
    aoi_bound: list[float] | None = None
    for event in audit_events:
        coverage = event.details.get("component_coverage") if event.kind == "task_inputs_resolved" else None
        if isinstance(coverage, dict):
            source_ids.update(str(key) for key in coverage)
        resolved_aoi = event.details.get("resolved_aoi") if event.kind == "task_inputs_resolved" else None
        if isinstance(resolved_aoi, dict) and isinstance(resolved_aoi.get("bbox"), list):
            aoi_bound = [float(value) for value in resolved_aoi["bbox"]]
    component_ids = contract.get("component_source_ids")
    if isinstance(component_ids, list):
        source_ids.update(str(item) for item in component_ids)
    bounded = job_type != "poi" or (
        {"raw.osm.poi", "raw.gns.poi"}.issubset(source_ids) and aoi_bound is not None
    )
    return {
        "supported": job_type == "poi",
        "bounded": bounded,
        "aoi_bound": aoi_bound,
        "source_ids": sorted(source_ids),
        "unsupported_boundary": "unbounded POI entity alignment is unsupported",
    }
```

- [ ] **Step 4: Write failing run report POI boundary test**

Append to `tests/test_run_report_service.py`:

```python
def test_run_report_includes_bounded_poi_quality_boundary(tmp_path: Path) -> None:
    artifact = tmp_path / "poi.gpkg"
    artifact.write_bytes(b"gpkg")
    status = _run_status(artifact).model_copy(update={"job_type": JobType.poi})
    plan = _plan().model_copy(
        update={
            "tasks": [
                _plan().tasks[0].model_copy(
                    update={
                        "input": _plan().tasks[0].input.model_copy(
                            update={"data_type_id": "dt.poi.bundle", "data_source_id": "catalog.generic.poi"}
                        ),
                        "output": _plan().tasks[0].output.model_copy(update={"data_type_id": "dt.poi.fused"}),
                    }
                )
            ]
        }
    )
    events = _audit_events() + [
        RunEvent(
            timestamp="2026-05-29T00:00:07+00:00",
            kind="task_inputs_resolved",
            phase=RunPhase.running,
            message="poi inputs",
            details={
                "resolved_aoi": {"display_name": "Nairobi, Kenya", "bbox": [36.65, -1.45, 37.10, -1.10]},
                "component_coverage": {
                    "raw.osm.poi": {"feature_count": 5},
                    "raw.gns.poi": {"feature_count": 2},
                },
            },
        )
    ]

    summary = build_run_report_summary(
        status=status,
        plan=plan,
        audit_events=events,
        artifact_path=artifact,
        source_semantic_contract={"component_source_ids": ["raw.osm.poi", "raw.gns.poi"]},
    )

    poi = summary["quality_summary"]["target_capability"]["target_5_bounded_poi"]
    assert poi["bounded"] is True
    assert poi["aoi_bound"] == [36.65, -1.45, 37.10, -1.10]
    assert "unbounded POI entity alignment is unsupported" in summary["evidence_readiness"]["boundary"]["poi"]
```

- [ ] **Step 5: Run POI report tests**

Run:

```powershell
py -3.13 -m pytest -q tests/test_report_quality_service.py::test_report_quality_summary_marks_bounded_poi_and_rejects_unbounded_claim tests/test_run_report_service.py::test_run_report_includes_bounded_poi_quality_boundary
```

Expected: PASS after Step 3 and Task 2 report integration are present.

- [ ] **Step 6: Update Target 2-6 evidence boundary doc**

Modify `docs/superpowers/specs/2026-05-28-targets-2-6-runtime-evidence-freeze.md` under `## Boundaries` to include this exact bullet:

```markdown
- Target 5 POI support is AOI-bounded OSM + GNS/GeoNames vector fusion; unbounded POI entity alignment, name disambiguation across unrelated regions, and global gazetteer deduplication remain unsupported.
```

- [ ] **Step 7: Run Task 3 tests**

Run:

```powershell
py -3.13 -m pytest -q tests/test_report_quality_service.py tests/test_run_report_service.py
```

Expected: PASS.

- [ ] **Step 8: Commit Task 3**

```powershell
git add services/report_quality_service.py tests/test_report_quality_service.py services/run_report_service.py tests/test_run_report_service.py docs/superpowers/specs/2026-05-28-targets-2-6-runtime-evidence-freeze.md
git commit -m "feat: clarify bounded poi evidence"
```

### Task 4: Add Source Materialization Manifests And Provider Fault Evidence

**Files:**
- Create: `services/source_materialization_manifest_service.py`
- Create: `tests/test_source_materialization_manifest_service.py`
- Modify: `services/input_acquisition_service.py`
- Modify: `tests/test_input_acquisition_service.py`
- Modify: `services/agent_run_service.py`
- Test: `tests/test_input_acquisition_faults.py`

- [ ] **Step 1: Write failing manifest service tests**

Create `tests/test_source_materialization_manifest_service.py`:

```python
from __future__ import annotations

from pathlib import Path

from services.source_materialization_manifest_service import (
    build_source_materialization_manifest,
    write_source_materialization_manifest,
)


def test_build_source_materialization_manifest_records_download_clip_and_provider_attempt() -> None:
    manifest = build_source_materialization_manifest(
        source_id="catalog.generic.poi",
        selected_source_id="catalog.generic.poi",
        source_mode="downloaded",
        cache_hit=False,
        version_token="gns-v1|osm-v1",
        target_crs="EPSG:4326",
        requested_bbox=(36.65, -1.45, 37.10, -1.10),
        materialized_bbox=(36.65, -1.45, 37.10, -1.10),
        component_coverage={
            "raw.osm.poi": {"feature_count": 5},
            "raw.gns.poi": {"feature_count": 2},
        },
        provider_attempts=[
            {"provider": "_StubBundleProvider", "source_id": "catalog.generic.poi", "outcome": "success"}
        ],
        fault=None,
    )

    assert manifest["source_id"] == "catalog.generic.poi"
    assert manifest["source_mode"] == "downloaded"
    assert manifest["cache_hit"] is False
    assert manifest["version_token"] == "gns-v1|osm-v1"
    assert manifest["requested_bbox"] == [36.65, -1.45, 37.10, -1.10]
    assert manifest["materialized_bbox"] == [36.65, -1.45, 37.10, -1.10]
    assert manifest["component_coverage"]["raw.gns.poi"]["feature_count"] == 2
    assert manifest["provider_attempts"][0]["outcome"] == "success"
    assert manifest["fault"] is None


def test_write_source_materialization_manifest_writes_utf8_json(tmp_path: Path) -> None:
    path = write_source_materialization_manifest(
        tmp_path / "source_materialization_manifest.json",
        {
            "source_id": "catalog.task.building.default",
            "source_mode": "clip_reused",
            "provider_attempts": [],
        },
    )

    assert path.name == "source_materialization_manifest.json"
    assert '"source_mode": "clip_reused"' in path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run manifest service tests to verify they fail**

Run:

```powershell
py -3.13 -m pytest -q tests/test_source_materialization_manifest_service.py
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement manifest service**

Create `services/source_materialization_manifest_service.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence


def build_source_materialization_manifest(
    *,
    source_id: str,
    selected_source_id: str | None,
    source_mode: str,
    cache_hit: bool,
    version_token: str,
    target_crs: str,
    requested_bbox: Sequence[float] | None,
    materialized_bbox: Sequence[float] | None,
    component_coverage: dict[str, object],
    provider_attempts: list[dict[str, object]],
    fault: str | None,
) -> dict[str, Any]:
    return {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_id": source_id,
        "selected_source_id": selected_source_id or source_id,
        "source_mode": source_mode,
        "cache_hit": bool(cache_hit),
        "version_token": version_token,
        "target_crs": target_crs,
        "requested_bbox": _bbox_list(requested_bbox),
        "materialized_bbox": _bbox_list(materialized_bbox),
        "component_coverage": component_coverage,
        "provider_attempts": provider_attempts,
        "fault": fault,
    }


def write_source_materialization_manifest(path: Path, manifest: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def _bbox_list(value: Sequence[float] | None) -> list[float] | None:
    if value is None:
        return None
    return [float(item) for item in value]
```

- [ ] **Step 4: Run manifest service tests**

Run:

```powershell
py -3.13 -m pytest -q tests/test_source_materialization_manifest_service.py
```

Expected: PASS.

- [ ] **Step 5: Add manifest path to `ResolvedRunInputs`**

Modify `services/input_acquisition_service.py`.

Add import:

```python
from services.source_materialization_manifest_service import (
    build_source_materialization_manifest,
    write_source_materialization_manifest,
)
```

Add field to `ResolvedRunInputs` dataclass:

```python
    source_materialization_manifest_path: Path | None = None
```

Add helper method to `InputAcquisitionService`:

```python
    def _write_manifest(
        self,
        *,
        manifest_dir: Path,
        source_id: str,
        selected_source_id: str | None,
        source_mode: str,
        cache_hit: bool,
        version_token: str,
        target_crs: str,
        requested_bbox: Optional[BBox],
        materialized_bbox: Optional[BBox],
        component_coverage: dict[str, object],
        provider_attempts: list[dict[str, object]],
        fault: str | None,
    ) -> Path:
        return write_source_materialization_manifest(
            manifest_dir / "source_materialization_manifest.json",
            build_source_materialization_manifest(
                source_id=source_id,
                selected_source_id=selected_source_id,
                source_mode=source_mode,
                cache_hit=cache_hit,
                version_token=version_token,
                target_crs=target_crs,
                requested_bbox=requested_bbox,
                materialized_bbox=materialized_bbox,
                component_coverage=component_coverage,
                provider_attempts=provider_attempts,
                fault=fault,
            ),
        )
```

When returning downloaded inputs after `_copy_cached_bundle(...)`, write manifest into `input_dir` and pass the path:

```python
        manifest_path = self._write_manifest(
            manifest_dir=input_dir,
            source_id=source_id,
            selected_source_id=materialized.source_id or source_id,
            source_mode="downloaded",
            cache_hit=False,
            version_token=version_token,
            target_crs=target_crs,
            requested_bbox=effective_request_bbox,
            materialized_bbox=bundle_bbox,
            component_coverage=_jsonable_component_coverage(materialized.component_coverage),
            provider_attempts=[
                {"provider": type(provider).__name__, "source_id": source_id, "outcome": "success"}
            ],
            fault=None,
        )
```

Set it in `ResolvedRunInputs(...)`:

```python
            source_materialization_manifest_path=manifest_path,
```

For `cache_reused` and `clip_reused` branches, write manifests into `input_dir` with `provider_attempts=[]`, `cache_hit=True`, and the matching `source_mode`.

- [ ] **Step 6: Write failing input acquisition manifest tests**

Append to `tests/test_input_acquisition_service.py`:

```python
def test_input_acquisition_writes_source_materialization_manifest_for_downloaded_bundle(tmp_path: Path) -> None:
    from services.input_acquisition_service import InputAcquisitionService

    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    provider = _StubBundleProvider(version_token="v1")
    service = InputAcquisitionService(registry=registry, providers=[provider], cache_dir=tmp_path / "cache")

    resolved = service.resolve_task_driven_inputs(
        request=_build_request(spatial_extent="bbox(1,1,2,2)"),
        source_id="catalog.task.building.default",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run",
    )

    assert resolved.source_materialization_manifest_path is not None
    payload = json.loads(resolved.source_materialization_manifest_path.read_text(encoding="utf-8"))
    assert payload["source_id"] == "catalog.task.building.default"
    assert payload["source_mode"] == "downloaded"
    assert payload["cache_hit"] is False
    assert payload["requested_bbox"] == [1.0, 1.0, 2.0, 2.0]
    assert payload["provider_attempts"][0]["outcome"] == "success"


def test_input_acquisition_writes_source_materialization_manifest_for_clip_reuse(tmp_path: Path) -> None:
    from services.input_acquisition_service import InputAcquisitionService

    registry = ArtifactRegistry(index_path=tmp_path / "artifact_registry.json")
    provider = _StubBundleProvider(version_token="v1")
    service = InputAcquisitionService(registry=registry, providers=[provider], cache_dir=tmp_path / "cache")

    service.resolve_task_driven_inputs(
        request=_build_request(),
        source_id="catalog.task.building.default",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run1",
    )
    reused = service.resolve_task_driven_inputs(
        request=_build_request(spatial_extent="bbox(1,1,2,2)"),
        source_id="catalog.task.building.default",
        required_output_type="dt.building.bundle",
        input_dir=tmp_path / "run2",
    )

    assert reused.source_materialization_manifest_path is not None
    payload = json.loads(reused.source_materialization_manifest_path.read_text(encoding="utf-8"))
    assert payload["source_mode"] == "clip_reused"
    assert payload["cache_hit"] is True
    assert payload["provider_attempts"] == []
    assert payload["requested_bbox"] == [1.0, 1.0, 2.0, 2.0]
```

Also add `import json` at the top of `tests/test_input_acquisition_service.py`.

- [ ] **Step 7: Run input manifest tests to verify they fail then pass**

Run before Step 5 implementation is complete:

```powershell
py -3.13 -m pytest -q tests/test_input_acquisition_service.py::test_input_acquisition_writes_source_materialization_manifest_for_downloaded_bundle tests/test_input_acquisition_service.py::test_input_acquisition_writes_source_materialization_manifest_for_clip_reuse
```

Expected before implementation: FAIL with `AttributeError: 'ResolvedRunInputs' object has no attribute 'source_materialization_manifest_path'`.

Run after Step 5 implementation:

```powershell
py -3.13 -m pytest -q tests/test_input_acquisition_service.py::test_input_acquisition_writes_source_materialization_manifest_for_downloaded_bundle tests/test_input_acquisition_service.py::test_input_acquisition_writes_source_materialization_manifest_for_clip_reuse
```

Expected after implementation: PASS.

- [ ] **Step 8: Propagate manifest path into run audit**

Modify `services/agent_run_service.py` in `_record_task_inputs_resolved()` after `version_token`:

```python
            "source_materialization_manifest_path": (
                str(resolved_inputs.source_materialization_manifest_path)
                if resolved_inputs.source_materialization_manifest_path is not None
                else None
            ),
```

- [ ] **Step 9: Write audit propagation assertion**

In `tests/test_agent_run_service_enhancements.py`, update `test_agent_run_service_task_driven_auto_prepares_inputs_before_execution`. When it constructs the `ResolvedRunInputs` object returned by `fake_resolve_task_driven_inputs`, add this field:

```python
        source_materialization_manifest_path=tmp_path / "runs" / "source_materialization_manifest.json",
```

Then add this assertion after `assert resolved_event.details["ref_zip_name"] == "ref.zip"`:

```python
    assert resolved_event.details["source_materialization_manifest_path"].endswith("source_materialization_manifest.json")
```

- [ ] **Step 10: Run Task 4 tests**

Run:

```powershell
py -3.13 -m pytest -q tests/test_source_materialization_manifest_service.py tests/test_input_acquisition_service.py tests/test_input_acquisition_faults.py tests/test_agent_run_service_enhancements.py
```

Expected: PASS.

- [ ] **Step 11: Commit Task 4**

```powershell
git add services/source_materialization_manifest_service.py tests/test_source_materialization_manifest_service.py services/input_acquisition_service.py tests/test_input_acquisition_service.py services/agent_run_service.py tests/test_agent_run_service_enhancements.py
git commit -m "feat: record source materialization manifests"
```

### Task 5: Upgrade Run Reports And Inspection API For Target 8

**Files:**
- Modify: `schemas/agent.py`
- Modify: `api/routers/runs_v2.py`
- Modify: `tests/test_api_v2_integration.py`
- Modify: `tests/test_run_report_service.py`

- [ ] **Step 1: Write failing API inspection test for report quality fields**

Append to `tests/test_api_v2_integration.py`:

```python
def test_run_inspection_exposes_report_quality_summary_from_saved_report(tmp_path: Path, client: TestClient, monkeypatch) -> None:
    from api.routers import runs_v2 as runs_v2_router
    from schemas.agent import RunPhase, RunStatus, RunTrigger, RunTriggerType
    from schemas.fusion import JobType

    run_id = "run-quality-api"
    runs_root = tmp_path / "runs"
    documents_dir = runs_root / run_id / "documents"
    documents_dir.mkdir(parents=True)
    (documents_dir / "run_report_summary.json").write_text(
        json.dumps(
            {
                "quality_summary": {
                    "evidence_readiness_score": 0.9,
                    "target_capability": {
                        "target_8_report": {"supported": True, "sections": ["process", "result", "quality"]}
                    },
                },
                "evidence_readiness": {"score": 0.9, "boundary": {"download": "provider availability is external"}},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    status = RunStatus(
        run_id=run_id,
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="inspect report quality"),
        phase=RunPhase.succeeded,
        progress=100,
        target_crs="EPSG:4326",
        created_at="2026-05-29T00:00:00+00:00",
        updated_at="2026-05-29T00:01:00+00:00",
    )

    class StubService:
        base_dir = runs_root

        def get_run(self, requested_run_id: str):
            return status if requested_run_id == run_id else None

        def get_plan(self, requested_run_id: str):
            return None

        def get_audit_events(self, requested_run_id: str):
            return []

        def get_artifact_path(self, requested_run_id: str):
            return None

    monkeypatch.setattr(runs_v2_router, "agent_run_service", StubService())

    response = client.get(f"/api/v2/runs/{run_id}/inspection")

    assert response.status_code == 200
    payload = response.json()
    assert payload["report_quality_summary"]["evidence_readiness_score"] == 0.9
    assert payload["evidence_readiness"]["score"] == 0.9
```

- [ ] **Step 2: Run API test to verify it fails**

Run:

```powershell
py -3.13 -m pytest -q tests/test_api_v2_integration.py::test_run_inspection_exposes_report_quality_summary_from_saved_report
```

Expected: FAIL with response validation errors or missing `report_quality_summary`.

- [ ] **Step 3: Extend inspection schema**

Modify `schemas/agent.py` in `RunInspectionResponse`:

```python
    report_quality_summary: Dict[str, Any] = Field(default_factory=dict)
    evidence_readiness: Dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Populate inspection fields**

Modify `api/routers/runs_v2.py` in `_build_run_inspection_response()` after `report_summary = _load_report_summary(run_id)`:

```python
    report_quality_summary = _dict_from_mapping(report_summary.get("quality_summary"))
    evidence_readiness = _dict_from_mapping(report_summary.get("evidence_readiness"))
```

Pass them into `RunInspectionResponse(...)`:

```python
        report_quality_summary=report_quality_summary,
        evidence_readiness=evidence_readiness,
```

- [ ] **Step 5: Strengthen Markdown report assertions**

Modify `tests/test_run_report_service.py::test_render_run_reports_writes_chinese_english_and_json_evidence` by adding:

```python
    assert "质量与证据边界" in zh
    assert "Quality And Evidence Boundary" in en
    assert "quality_summary" in evidence
    assert "evidence_readiness" in evidence
```

- [ ] **Step 6: Run Task 5 tests**

Run:

```powershell
py -3.13 -m pytest -q tests/test_api_v2_integration.py::test_run_inspection_exposes_report_quality_summary_from_saved_report tests/test_run_report_service.py
```

Expected: PASS.

- [ ] **Step 7: Commit Task 5**

```powershell
git add schemas/agent.py api/routers/runs_v2.py tests/test_api_v2_integration.py tests/test_run_report_service.py
git commit -m "feat: expose report quality evidence"
```

### Task 6: Strengthen Automatic Error Handling And Recovery Evidence

**Files:**
- Modify: `services/run_recovery_service.py`
- Modify: `tests/test_run_recovery_service.py`
- Modify: `services/run_report_service.py`
- Modify: `tests/test_run_report_service.py`

- [ ] **Step 1: Write failing recovery hint tests for operator action**

Append to `tests/test_run_recovery_service.py`:

```python
def test_build_recovery_hint_includes_operator_action_for_recoverable_download_failure() -> None:
    hint = build_recovery_hint(
        {
            "phase": "failed",
            "checkpoint": {"stage": "execution"},
            "failure_summary": "download timed out while materializing inputs | failure_category=SOURCE_DOWNLOAD_FAILED",
        }
    )

    assert hint["recoverable"] is True
    assert hint["recovery_action"] == "redispatch_from_execution"
    assert hint["operator_action"] == "no manual action required; recovery worker can redispatch from execution"
    assert hint["classification_evidence"]["failure_category"] == "SOURCE_DOWNLOAD_FAILED"


def test_build_recovery_hint_includes_operator_action_for_manual_review_failure() -> None:
    hint = build_recovery_hint(
        {
            "phase": "failed",
            "checkpoint": {"stage": "execution"},
            "failure_summary": "parameter out of range | failure_category=PARAM_OUT_OF_RANGE",
        }
    )

    assert hint["recoverable"] is False
    assert hint["recovery_action"] == "none"
    assert hint["operator_action"] == "manual review required before rerun"
    assert hint["classification_evidence"]["phase"] == "failed"
```

- [ ] **Step 2: Run recovery tests to verify they fail**

Run:

```powershell
py -3.13 -m pytest -q tests/test_run_recovery_service.py::test_build_recovery_hint_includes_operator_action_for_recoverable_download_failure tests/test_run_recovery_service.py::test_build_recovery_hint_includes_operator_action_for_manual_review_failure
```

Expected: FAIL with `KeyError: 'operator_action'`.

- [ ] **Step 3: Implement operator action and classification evidence**

Modify `services/run_recovery_service.py` by adding:

```python
def _operator_action_for_recovery(*, recoverable: bool, action: str, reason: str) -> str:
    if recoverable:
        if action == "redispatch_full_run":
            return "no manual action required; recovery worker can redispatch the full run"
        if action == "redispatch_from_validation":
            return "no manual action required; recovery worker can redispatch from validation"
        if action == "redispatch_from_execution":
            return "no manual action required; recovery worker can redispatch from execution"
    if reason == "manual_review_required":
        return "manual review required before rerun"
    return "inspect run state before rerun"
```

In `build_recovery_hint()`, after `reason` is computed, add:

```python
    operator_action = _operator_action_for_recovery(recoverable=recoverable, action=action, reason=reason)
```

Add these fields to `payload`:

```python
        "operator_action": operator_action,
        "classification_evidence": {
            "phase": str(run_payload.get("phase") or "").strip().lower(),
            "checkpoint_stage": str(checkpoint.get("stage") or "").strip().lower(),
            "resume_stage": str(checkpoint.get("resume_stage") or "").strip().lower(),
            "failure_category": failure_category,
        },
```

- [ ] **Step 4: Run recovery tests**

Run:

```powershell
py -3.13 -m pytest -q tests/test_run_recovery_service.py
```

Expected: PASS.

- [ ] **Step 5: Write failing report recovery quality assertion**

Append to `tests/test_run_report_service.py`:

```python
def test_run_report_quality_summary_includes_recovery_operator_action(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.gpkg"
    artifact.write_bytes(b"gpkg")
    status = _run_status(artifact).model_copy(
        update={
            "phase": RunPhase.failed,
            "failure_summary": "download timed out | failure_category=SOURCE_DOWNLOAD_FAILED",
            "checkpoint": {"stage": "execution"},
        }
    )

    summary = build_run_report_summary(
        status=status,
        plan=_plan(),
        audit_events=_audit_events(),
        artifact_path=artifact,
    )

    recovery = summary["quality_summary"]["target_capability"]["target_9_recovery"]
    assert recovery["recoverable"] is True
    assert recovery["recovery_action"] == "redispatch_from_execution"
    assert recovery["operator_action"] == "no manual action required; recovery worker can redispatch from execution"
```

- [ ] **Step 6: Run report recovery test**

Run:

```powershell
py -3.13 -m pytest -q tests/test_run_report_service.py::test_run_report_quality_summary_includes_recovery_operator_action
```

Expected: PASS after Step 3 and Task 2 quality integration are present.

- [ ] **Step 7: Run Task 6 tests**

Run:

```powershell
py -3.13 -m pytest -q tests/test_run_recovery_service.py tests/test_run_recovery_executor.py tests/test_worker_recovery_tick.py tests/test_run_report_service.py
```

Expected: PASS.

- [ ] **Step 8: Commit Task 6**

```powershell
git add services/run_recovery_service.py tests/test_run_recovery_service.py services/run_report_service.py tests/test_run_report_service.py
git commit -m "feat: clarify automatic recovery evidence"
```

### Task 7: Freeze Evidence And Update Research Summary

**Files:**
- Create: `docs/superpowers/specs/2026-05-29-targets-1-2-5-7-9-gap-closure-evidence.md`
- Create: `docs/superpowers/specs/2026-05-29-targets-1-2-5-7-9-gap-closure-evidence.json`
- Create: `tests/test_targets_1_2_5_7_9_gap_closure_evidence.py`
- Modify: `文档/研究总结0529.md`

- [ ] **Step 1: Write failing evidence guard test**

Create `tests/test_targets_1_2_5_7_9_gap_closure_evidence.py`:

```python
from __future__ import annotations

import json
from pathlib import Path


EVIDENCE_JSON = Path("docs/superpowers/specs/2026-05-29-targets-1-2-5-7-9-gap-closure-evidence.json")
EVIDENCE_MD = Path("docs/superpowers/specs/2026-05-29-targets-1-2-5-7-9-gap-closure-evidence.md")
RESEARCH_SUMMARY = Path("文档/研究总结0529.md")


def test_gap_closure_evidence_json_records_targets_and_boundaries() -> None:
    payload = json.loads(EVIDENCE_JSON.read_text(encoding="utf-8"))

    assert payload["date"] == "2026-05-29"
    assert payload["targets"]["1"]["claim"] == "unattended_local_operation_supported_with_scheduler_inbox_and_recovery_evidence"
    assert payload["targets"]["2"]["height_raster_evidence"] == "explicit_in_report_quality_summary"
    assert payload["targets"]["5"]["boundary"] == "bounded_aoi_poi_only"
    assert payload["targets"]["7"]["manifest"] == "source_materialization_manifest.json"
    assert payload["targets"]["8"]["reports"] == ["run_report_summary.json", "run_report.zh.md", "run_report.en.md"]
    assert payload["targets"]["9"]["operator_action"] == "included_in_recovery_hint"
    assert payload["non_claims"]["target_10"] == "bounded_policy_hints_only_no_self_mutating_model"


def test_gap_closure_docs_do_not_overclaim_self_learning_or_unbounded_poi() -> None:
    text = EVIDENCE_MD.read_text(encoding="utf-8") + "\n" + RESEARCH_SUMMARY.read_text(encoding="utf-8")

    forbidden = [
        "自动更新模型权重",
        "完全自主学习",
        "无边界POI实体对齐",
        "全球POI自动消歧已完成",
    ]
    for phrase in forbidden:
        assert phrase not in text

    assert "bounded policy hints only" in text
    assert "AOI-bounded OSM + GNS/GeoNames" in text
```

- [ ] **Step 2: Run evidence guard test to verify it fails**

Run:

```powershell
py -3.13 -m pytest -q tests/test_targets_1_2_5_7_9_gap_closure_evidence.py
```

Expected: FAIL with missing evidence files.

- [ ] **Step 3: Create machine-readable evidence JSON**

Create `docs/superpowers/specs/2026-05-29-targets-1-2-5-7-9-gap-closure-evidence.json`:

```json
{
  "date": "2026-05-29",
  "scope": "targets_1_2_5_7_8_9_gap_closure",
  "targets": {
    "1": {
      "claim": "unattended_local_operation_supported_with_scheduler_inbox_and_recovery_evidence",
      "evidence": [
        "scheduled_tick task_driven_auto spec_results",
        "watch_scenario_inbox evidence_json",
        "unattended_runtime_snapshot",
        "recovery_tick worker evidence"
      ],
      "boundary": "process supervision and external scheduler uptime are environment responsibilities"
    },
    "2": {
      "claim": "building_vector_fusion_with_optional_height_raster_is_auditable",
      "height_raster_evidence": "explicit_in_report_quality_summary",
      "boundary": "height raster must be present in source semantic contract or component coverage to claim participation"
    },
    "5": {
      "claim": "bounded_osm_gns_geonames_poi_fusion_supported",
      "boundary": "bounded_aoi_poi_only",
      "unsupported": "unbounded POI entity alignment remains unsupported"
    },
    "7": {
      "claim": "automatic_download_cache_clip_supported_for_registered_providers",
      "manifest": "source_materialization_manifest.json",
      "boundary": "provider availability is external and fault classes are recorded"
    },
    "8": {
      "claim": "run_reports_include_process_result_quality_and_boundary_assessment",
      "reports": ["run_report_summary.json", "run_report.zh.md", "run_report.en.md"]
    },
    "9": {
      "claim": "recoverable_failures_are_classified_for_worker_redispatch",
      "operator_action": "included_in_recovery_hint",
      "boundary": "manual review remains required for unsupported or ambiguous failure categories"
    }
  },
  "non_claims": {
    "target_10": "bounded_policy_hints_only_no_self_mutating_model",
    "poi": "no_unbounded_global_entity_alignment",
    "download": "no_guarantee_of_provider_uptime"
  }
}
```

- [ ] **Step 4: Create human-readable evidence Markdown**

Create `docs/superpowers/specs/2026-05-29-targets-1-2-5-7-9-gap-closure-evidence.md`:

```markdown
# Targets 1,2,5,7-9 Gap Closure Evidence

## Capability State

- Target 1: unattended local operation is supported through scheduled `task_driven_auto` runs, local scenario inbox processing, recovery tick scanning, and unattended runtime snapshots.
- Target 2: building vector fusion remains the core capability; height raster participation is auditable when raster sources appear in the source semantic contract or component coverage.
- Target 5: POI fusion is AOI-bounded OSM + GNS/GeoNames vector fusion.
- Target 7: automatic data download, cache reuse, clipping, version tokens, provider attempts, and fault classes are recorded through `source_materialization_manifest.json`.
- Target 8: run reports include process evaluation, result evaluation, source coverage, quality summary, evidence readiness, and boundary statements.
- Target 9: recovery hints classify recoverable failures, recovery action, operator action, failure category, and worker history evidence.

## Boundaries

- Target 10 remains bounded policy hints only; no automatic model, policy, or source catalog mutation is claimed.
- AOI-bounded OSM + GNS/GeoNames POI fusion is supported; unbounded POI entity alignment remains unsupported.
- Provider availability is external. Download manifests record cache behavior, retry/fault evidence, and source mode but do not guarantee live provider uptime.
- Long-running operation depends on process supervision and scheduler uptime supplied by the deployment environment.

## Verification Commands

- `py -3.13 -m pytest -q tests/test_unattended_run_monitor_service.py tests/test_worker_orchestration.py tests/test_watch_scenario_inbox.py`
- `py -3.13 -m pytest -q tests/test_report_quality_service.py tests/test_run_report_service.py`
- `py -3.13 -m pytest -q tests/test_source_materialization_manifest_service.py tests/test_input_acquisition_service.py tests/test_input_acquisition_faults.py`
- `py -3.13 -m pytest -q tests/test_run_recovery_service.py tests/test_run_recovery_executor.py tests/test_worker_recovery_tick.py`
- `py -3.13 -m pytest -q tests/test_targets_1_2_5_7_9_gap_closure_evidence.py`
```

- [ ] **Step 5: Append research summary section**

Append to `文档/研究总结0529.md`:

```markdown

## 0529 目标 1、2、5、7-9 差距补齐计划摘要

本轮补齐工作的研究定位不是重新设计融合算法，而是把已有建筑物、道路、水系、POI 与大范围拼接裁剪能力推进到可无人值守运行、可审计、可报告、可恢复的智能体系统状态。核心思路是围绕运行链路增加证据层：调度与 inbox 证明任务可以自动进入系统，source materialization manifest 证明数据可自动下载、缓存、裁剪并记录故障，report quality summary 证明报告能够同时覆盖过程评估和结果评估，recovery hint 证明错误能够被分类并给出自动恢复或人工复核动作。

能力边界需要在论文材料中保持清晰：Target 10 当前是 bounded policy hints only，不声称自动更新模型权重或自主改写知识库；POI 能力是 AOI-bounded OSM + GNS/GeoNames 融合，不声称无边界 POI 实体对齐；自动下载能力受外部数据源可用性影响，因此以 provider attempt、cache_hit、source_mode、fault classification 作为可复现实验证据。

该补齐计划完成后，论文的研究背景、系统方法、工程实现、实验设置和消融实验条件可以同步展开：实验变量包括是否启用自动下载、是否启用高度栅格、是否启用大范围 tile/stitch、是否启用恢复 worker、是否启用质量报告；评价指标包括任务成功率、人工介入次数、下载/缓存命中情况、融合产物有效性、报告完整性和错误恢复有效性。
```

- [ ] **Step 6: Run evidence guard test**

Run:

```powershell
py -3.13 -m pytest -q tests/test_targets_1_2_5_7_9_gap_closure_evidence.py
```

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

```powershell
git add docs/superpowers/specs/2026-05-29-targets-1-2-5-7-9-gap-closure-evidence.md docs/superpowers/specs/2026-05-29-targets-1-2-5-7-9-gap-closure-evidence.json tests/test_targets_1_2_5_7_9_gap_closure_evidence.py 文档/研究总结0529.md
git commit -m "docs: freeze gap closure evidence"
```

## Final Verification Gate

- [ ] **Step 1: Run focused target gap tests**

```powershell
py -3.13 -m pytest -q tests/test_unattended_run_monitor_service.py tests/test_worker_orchestration.py tests/test_watch_scenario_inbox.py tests/test_report_quality_service.py tests/test_source_materialization_manifest_service.py tests/test_input_acquisition_service.py tests/test_run_recovery_service.py tests/test_run_report_service.py tests/test_targets_1_2_5_7_9_gap_closure_evidence.py
```

Expected: PASS.

- [ ] **Step 2: Run representative existing closure tests**

```powershell
py -3.13 -m pytest -q tests/test_large_area_runtime_service.py tests/test_agent_run_service_large_area_runtime.py tests/test_agent_run_service_multisource_building_runtime.py tests/test_source_asset_service.py tests/test_fusioncode_poi.py tests/test_track_b_national_scale_service.py tests/test_track_b_national_v7_routes.py
```

Expected: PASS.

- [ ] **Step 3: Run full test suite**

```powershell
py -3.13 -m pytest -q
```

Expected while this implementation plan remains active: the functional suite should pass, and `tests/test_plan_handshake.py::test_completed_master_plan_is_archived_with_no_active_plan_left` is expected to fail because `docs/superpowers/plans/2026-05-29-fusionagent-targets-1-2-5-7-9-gap-closure.md` is an active plan file. After implementation is complete and this plan is archived to `docs/superpowers/plans/done/`, rerun `py -3.13 -m pytest -q tests/test_plan_handshake.py` and expect PASS.

- [ ] **Step 4: Self-review claim boundaries**

Run:

```powershell
rg -n "自动更新模型权重|完全自主学习|无边界POI|全球POI自动消歧已完成|unbounded POI entity alignment is supported" docs 文档 tests services
```

Expected: no matches that make a positive unsupported claim. Mentions in forbidden-phrase tests are acceptable.

- [ ] **Step 5: Final implementation note**

After implementation, report:

- files changed by task,
- focused and full test results,
- whether Target 1,2,5,7,8,9 gaps are closed,
- remaining boundary for Target 10,
- provider-dependent download caveat,
- any residual unrelated dirty worktree items that were not touched.
