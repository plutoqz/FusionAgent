# GPKG Canonical Output And Quality Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Prefer `gpt-5.5` workers. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote GPKG to the canonical fusion output and add a quality gate that accepts or rejects outputs based on non-empty/readability, AOI consistency, geometry type, required fields, source lineage, and multi-source contribution where required.

**Architecture:** Keep compatibility zip/shapefile packaging for existing consumers, but make the canonical artifact inside the run output a GPKG. Add a `QualityGateService` that reads vector artifacts and produces `quality_report.json`. `AgentRunService` calls it after schema validation and before declaring a run succeeded. Scenario summaries aggregate child quality reports.

**Tech Stack:** Python, GeoPandas, pytest, existing `evaluate_vector_artifact`, `AgentRunService`, `ScenarioRunService`, and output schema policies.

---

## Phase 0: Documentation Discovery

### Sources Consulted

- `services/agent_run_service.py`
  - `_zip_output_artifact()` already handles `.gpkg` differently from shapefiles.
  - `_validate_output_artifact_against_schema_policy()` currently uses `evaluate_vector_artifact()`.
- `services/artifact_evaluation_service.py`
  - Current evaluation reads a vector path and checks non-empty plus required fields.
- `services/scenario_run_service.py`
  - Scenario currently checks zip path existence for non-shapefile outputs.
- `services/report_quality_service.py`
  - Existing report quality score is evidence-readiness, not acceptance.
- `tests/test_artifact_evaluation_service.py`
  - Existing fixture patterns for polygon and line vector evaluation.
- `tests/test_large_area_runtime_service.py`
  - Existing runners already write GPKG in some paths.

### Allowed APIs

- Use GeoPandas `gpd.read_file()` for GPKG and shapefile.
- Continue writing compatibility zip artifacts.
- Add `quality_report.json` under each run output directory.
- Fail a run after execution if quality gate rejects the canonical output.

### Anti-Pattern Guards

- Do not treat artifact existence as acceptance.
- Do not require water/POI to spatially fill the AOI; require query coverage evidence and explain sparse output.
- Do not remove compatibility exports.
- Do not add a new run phase.

## File Structure

- Create: `schemas/quality_gate.py`
- Create: `services/quality_gate_service.py`
- Modify: `services/artifact_evaluation_service.py`
- Modify: `services/agent_run_service.py`
- Modify: `services/scenario_run_service.py`
- Test: `tests/test_quality_gate_service.py`
- Test: `tests/test_artifact_evaluation_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`
- Test: `tests/test_scenario_run_service.py`

---

### Task 1: Extend Vector Evaluation To GPKG And AOI Checks

**Files:**
- Modify: `services/artifact_evaluation_service.py`
- Test: `tests/test_artifact_evaluation_service.py`

- [ ] **Step 1: Add failing tests**

Append:

```python
def test_evaluate_vector_artifact_reads_gpkg_layer(tmp_path):
    gpkg_path = _write_polygon_fixture(tmp_path / "buildings.gpkg", count=2, crs="EPSG:4326")

    metrics = evaluate_vector_artifact(gpkg_path, required_fields=["geometry", "fid"])

    assert metrics["artifact_validity"] is True
    assert metrics["feature_count"] == 2
    assert metrics["bbox"]


def test_evaluate_vector_artifact_reports_aoi_containment(tmp_path):
    gpkg_path = _write_polygon_fixture(tmp_path / "buildings.gpkg", count=1, crs="EPSG:4326")

    metrics = evaluate_vector_artifact(
        gpkg_path,
        required_fields=["geometry"],
        requested_bbox=(-1.0, -1.0, 20.0, 20.0),
    )

    assert metrics["aoi_consistency"]["requested_bbox"] == [-1.0, -1.0, 20.0, 20.0]
    assert metrics["aoi_consistency"]["artifact_intersects_aoi"] is True
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_artifact_evaluation_service.py::test_evaluate_vector_artifact_reads_gpkg_layer tests/test_artifact_evaluation_service.py::test_evaluate_vector_artifact_reports_aoi_containment -q
```

Expected: second test fails because `requested_bbox` parameter is unsupported.

- [ ] **Step 3: Update evaluation function**

Change signature:

```python
def evaluate_vector_artifact(
    shp_path: Path,
    *,
    required_fields: list[str],
    requested_bbox: list[float] | tuple[float, float, float, float] | None = None,
) -> dict[str, Any]:
```

After bbox calculation, add:

```python
    if requested_bbox is not None:
        metrics["aoi_consistency"] = _aoi_consistency(metrics.get("bbox"), requested_bbox)
```

Add helper:

```python
def _aoi_consistency(artifact_bbox: list[float] | None, requested_bbox) -> dict[str, Any]:
    requested = [float(value) for value in requested_bbox]
    if artifact_bbox is None:
        return {
            "requested_bbox": requested,
            "artifact_intersects_aoi": False,
            "artifact_bbox": None,
        }
    aminx, aminy, amaxx, amaxy = artifact_bbox
    rminx, rminy, rmaxx, rmaxy = requested
    intersects = not (amaxx < rminx or aminx > rmaxx or amaxy < rminy or aminy > rmaxy)
    return {
        "requested_bbox": requested,
        "artifact_intersects_aoi": intersects,
        "artifact_bbox": artifact_bbox,
    }
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_artifact_evaluation_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/artifact_evaluation_service.py tests/test_artifact_evaluation_service.py
git commit -m "feat: evaluate gpkg artifacts with aoi evidence"
```

### Task 2: Add Quality Gate Service

**Files:**
- Create: `schemas/quality_gate.py`
- Create: `services/quality_gate_service.py`
- Test: `tests/test_quality_gate_service.py`

- [ ] **Step 1: Write failing service tests**

Create `tests/test_quality_gate_service.py`:

```python
from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Point, Polygon

from schemas.task_kind import TaskKind
from services.quality_gate_service import QualityGateService


def test_quality_gate_accepts_multisource_building_gpkg(tmp_path: Path) -> None:
    path = tmp_path / "building.gpkg"
    frame = gpd.GeoDataFrame(
        {"source_id": ["raw.osm.building", "raw.microsoft.building"], "confidence": [0.9, 0.8]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)]), Polygon([(2, 0), (2, 1), (3, 1), (3, 0)])],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.building,
        required_fields=["geometry", "source_id"],
        requested_bbox=(-1, -1, 4, 2),
        component_coverage={
            "raw.osm.building": {"feature_count": 1, "coverage_status": "available"},
            "raw.microsoft.building": {"feature_count": 1, "coverage_status": "available"},
        },
    )

    assert report.accepted is True
    assert report.checks["non_empty"]["passed"] is True
    assert report.checks["multi_source_lineage"]["passed"] is True


def test_quality_gate_rejects_wrong_geometry_for_waterways(tmp_path: Path) -> None:
    path = tmp_path / "waterways.gpkg"
    frame = gpd.GeoDataFrame({"source_id": ["raw.osm.waterways"]}, geometry=[Point(0, 0)], crs="EPSG:4326")
    frame.to_file(path, driver="GPKG")

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.waterways,
        required_fields=["geometry", "source_id"],
        requested_bbox=(-1, -1, 1, 1),
        component_coverage={"raw.osm.waterways": {"feature_count": 1, "coverage_status": "available"}},
    )

    assert report.accepted is False
    assert report.checks["geometry_type"]["passed"] is False
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_quality_gate_service.py -q
```

Expected: FAIL because quality gate does not exist.

- [ ] **Step 3: Implement schemas**

Create `schemas/quality_gate.py`:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from schemas.task_kind import TaskKind


class QualityGateReport(BaseModel):
    accepted: bool
    task_kind: TaskKind
    artifact_path: str
    checks: dict[str, dict[str, Any]] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Implement service**

Create `services/quality_gate_service.py`:

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from schemas.quality_gate import QualityGateReport
from schemas.task_kind import TaskKind
from services.artifact_evaluation_service import evaluate_vector_artifact

_EXPECTED_GEOMETRIES = {
    TaskKind.building: {"Polygon", "MultiPolygon"},
    TaskKind.road: {"LineString", "MultiLineString"},
    TaskKind.water_polygon: {"Polygon", "MultiPolygon"},
    TaskKind.waterways: {"LineString", "MultiLineString"},
    TaskKind.poi: {"Point", "MultiPoint"},
}


class QualityGateService:
    def evaluate(
        self,
        *,
        artifact_path: Path,
        task_kind: TaskKind,
        required_fields: list[str],
        requested_bbox=None,
        component_coverage: dict[str, object] | None = None,
    ) -> QualityGateReport:
        metrics = evaluate_vector_artifact(
            Path(artifact_path),
            required_fields=required_fields,
            requested_bbox=requested_bbox,
        )
        checks = {
            "readable": {"passed": "error" not in metrics},
            "non_empty": {"passed": int(metrics.get("feature_count") or 0) > 0},
            "required_fields": {"passed": not metrics.get("missing_fields")},
            "geometry_type": {
                "passed": bool(set(metrics.get("geometry_types") or []) & _EXPECTED_GEOMETRIES[task_kind]),
                "expected": sorted(_EXPECTED_GEOMETRIES[task_kind]),
                "actual": metrics.get("geometry_types") or [],
            },
            "aoi_intersection": {
                "passed": bool(metrics.get("aoi_consistency", {}).get("artifact_intersects_aoi", requested_bbox is None)),
            },
            "source_lineage": {
                "passed": "source_id" in required_fields and "source_id" not in metrics.get("missing_fields", []),
            },
            "multi_source_lineage": {
                "passed": _multi_source_lineage_available(component_coverage or {}),
            },
        }
        accepted = all(check["passed"] for check in checks.values())
        return QualityGateReport(
            accepted=accepted,
            task_kind=task_kind,
            artifact_path=str(artifact_path),
            checks=checks,
            metrics=metrics,
        )


def _multi_source_lineage_available(component_coverage: dict[str, object]) -> bool:
    available = []
    for source_id, payload in component_coverage.items():
        if isinstance(payload, dict):
            count = payload.get("feature_count")
            status = str(payload.get("coverage_status") or "")
            if status in {"available", "unknown_until_materialization"} or (count is not None and int(count) > 0):
                available.append(source_id)
    return len(set(available)) >= 2
```

- [ ] **Step 5: Verify**

```powershell
py -3.13 -m pytest tests/test_quality_gate_service.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add schemas/quality_gate.py services/quality_gate_service.py tests/test_quality_gate_service.py
git commit -m "feat: add vector quality gate"
```

### Task 3: Write Quality Report In Run Writeback

**Files:**
- Modify: `services/agent_run_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`

- [ ] **Step 1: Add failing run writeback test**

Add this test near other writeback/schema validation tests in `tests/test_agent_run_service_enhancements.py`:

```python
def test_agent_run_service_writes_quality_report_for_gpkg_output(tmp_path: Path) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content="building",
            spatial_extent="bbox(0,0,1,1)",
        ),
        target_crs="EPSG:4326",
        field_mapping={},
        debug=False,
    )
    plan = _build_plan(workflow_id="wf_quality_gate", revision=1)
    run_id = "run-quality-gate"
    _seed_run_status(service, run_id, request)
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    fused_gpkg = output_dir / "building_fusion_result.gpkg"
    gpd.GeoDataFrame(
        {"fid": [1], "source_count": [2]},
        geometry=[box(0.1, 0.1, 0.9, 0.9)],
        crs="EPSG:4326",
    ).to_file(fused_gpkg, driver="GPKG")

    service.run_writeback_stage(
        run_id=run_id,
        request=request,
        plan=plan,
        fused_shp=fused_gpkg,
        repair_records=[],
        output_dir=output_dir,
    )

    quality_report_path = output_dir / "quality_report.json"
    assert quality_report_path.exists()
    payload = json.loads(quality_report_path.read_text(encoding="utf-8"))
    assert payload["accepted"] is True
    assert payload["task_kind"] == "building"
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_agent_run_service_enhancements.py::test_agent_run_service_writes_quality_report_for_gpkg_output -q
```

Expected: FAIL because no quality report is written.

- [ ] **Step 3: Implement writeback quality gate**

In `services/agent_run_service.py`, instantiate `QualityGateService`.

Add these module-level helpers above `class AgentRunService`:

```python
def _task_kind_for_request(request: RunCreateRequest) -> TaskKind:
    task_kind_value = getattr(request, "task_kind", None)
    if task_kind_value:
        return task_kind_value if isinstance(task_kind_value, TaskKind) else TaskKind(str(task_kind_value))
    preferred = str(getattr(request, "preferred_pattern_id", "") or "")
    if "waterways" in preferred:
        return TaskKind.waterways
    if "water_polygon" in preferred:
        return TaskKind.water_polygon
    if request.job_type == JobType.water:
        return TaskKind.water_polygon
    return TaskKind(request.job_type.value)


def _component_coverage_from_status(status: RunStatus | None) -> dict[str, object]:
    if status is None:
        return {}
    checkpoint = getattr(status, "checkpoint", None) or {}
    coverage = checkpoint.get("component_coverage") if isinstance(checkpoint, dict) else None
    if isinstance(coverage, dict):
        return coverage
    telemetry = getattr(status, "planning_telemetry", None) or {}
    coverage = telemetry.get("component_coverage") if isinstance(telemetry, dict) else None
    return coverage if isinstance(coverage, dict) else {}
```

Add this instance helper near `_validate_output_artifact_against_schema_policy()`:

```python

def _required_fields_for_plan(self, plan: WorkflowPlan) -> list[str]:
    output_data_type = self._extract_output_data_type(plan)
    raw_policy = ArtifactReuseService._output_schema_policy(plan, required_output_type=output_data_type)
    schema_policy = self.kg_repo.get_output_schema_policy(output_data_type) if output_data_type else None
    if raw_policy is not None:
        return list(raw_policy.get("required_fields", []) or ["geometry"])
    if schema_policy is not None:
        return list(schema_policy.required_fields)
    return ["geometry"]
```

After `_validate_output_artifact_against_schema_policy()` and before `_zip_output_artifact()`, call:

```python
quality_report = self.quality_gate_service.evaluate(
    artifact_path=fused_shp,
    task_kind=_task_kind_for_request(request),
    required_fields=_required_fields_for_plan(plan),
    requested_bbox=self._parse_bbox(request.trigger.spatial_extent),
    component_coverage=_component_coverage_from_status(self.get_run(run_id)),
)
quality_report_path = output_dir / "quality_report.json"
quality_report_path.write_text(
    json.dumps(quality_report.model_dump(mode="json"), ensure_ascii=False, indent=2),
    encoding="utf-8",
)
self._update_status(
    run_id,
    RunPhase.running,
    progress=92,
    plan_revision=self._extract_plan_revision(plan),
    checkpoint=self._checkpoint(stage="quality_gate", plan_revision=self._extract_plan_revision(plan)),
    event_kind="quality_gate_evaluated",
    event_message="Fusion output evaluated by quality gate.",
    event_details={
        "accepted": quality_report.accepted,
        "path": str(quality_report_path),
        "failure_reasons": quality_report.failure_reasons,
    },
)
if not quality_report.accepted:
    raise RuntimeError("Quality gate rejected fusion output")
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_quality_gate_service.py tests/test_agent_run_service_enhancements.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/agent_run_service.py tests/test_agent_run_service_enhancements.py
git commit -m "feat: run quality gate during writeback"
```

### Task 4: Aggregate Quality Reports In Scenarios

**Files:**
- Modify: `services/scenario_run_service.py`
- Test: `tests/test_scenario_run_service.py`

- [ ] **Step 1: Add failing scenario summary assertion**

In `_FakeAgentRunService.create_run()` in `tests/test_scenario_run_service.py`, write a quality report next to each fake artifact:

```python
quality_report = {
    "task_kind": task_key.replace("-", "_"),
    "accepted": True,
    "failure_reasons": [],
}
(artifact.parent / f"{run_id}_quality_report.json").write_text(
    json.dumps(quality_report, ensure_ascii=False, indent=2),
    encoding="utf-8",
)
```

Then in `test_scenario_run_service_starts_all_children_before_waiting_for_terminal_state`, add:

```python
assert summary["quality"]["accepted_child_count"] == 5
assert summary["quality"]["rejected_child_count"] == 0
assert [item["task_kind"] for item in summary["quality"]["child_reports"]] == fake.created_task_kinds
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_scenario_run_service.py::test_scenario_run_service_starts_all_children_before_waiting_for_terminal_state -q
```

Expected: FAIL because scenario summary has no `quality` section.

- [ ] **Step 3: Implement aggregation**

Add helper in `services/scenario_run_service.py`:

```python
def _load_child_quality_report(result: dict[str, Any]) -> dict[str, Any] | None:
    artifact_path = result.get("artifact_path")
    if not artifact_path:
        return None
    artifact = Path(artifact_path)
    candidates = [
        artifact.parent / "quality_report.json",
        artifact.parent / f"{artifact.stem}_quality_report.json",
    ]
    run_id = result.get("run_id")
    if run_id:
        candidates.append(artifact.parent / f"{run_id}_quality_report.json")
    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(payload, dict):
            payload.setdefault("run_id", result.get("run_id"))
            payload.setdefault("job_type", result.get("job_type"))
            payload.setdefault("task_kind", result.get("task_kind") or result.get("job_type"))
            return payload
    return None


def _quality_summary_from_children(child_results: list[dict[str, Any]]) -> dict[str, Any]:
    reports = []
    for result in child_results:
        report = _load_child_quality_report(result)
        if report is not None:
            reports.append(report)
    return {
        "accepted_child_count": sum(1 for report in reports if report.get("accepted") is True),
        "rejected_child_count": sum(1 for report in reports if report.get("accepted") is False),
        "child_reports": reports,
    }
```

Add `"quality": _quality_summary_from_children(child_results)` to `_build_summary()`.

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_scenario_run_service.py tests/test_quality_gate_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/scenario_run_service.py tests/test_scenario_run_service.py
git commit -m "feat: aggregate scenario quality reports"
```

### Task 5: Final Verification

- [ ] **Step 1: Focused tests**

```powershell
py -3.13 -m pytest tests/test_artifact_evaluation_service.py tests/test_quality_gate_service.py tests/test_agent_run_service_enhancements.py tests/test_scenario_run_service.py tests/test_run_report_service.py -q
```

Expected: PASS.

- [ ] **Step 2: Anti-pattern scans**

```powershell
rg -n "artifact_validity\": bool\\(artifact_path|Path\\(artifact_path\\)\\.exists\\(\\)" services/scenario_run_service.py services/run_report_service.py
```

Expected: existing report summaries may still expose path existence, but scenario quality acceptance must use `quality_report.json`.

```powershell
rg -n "QualityGateService|quality_gate_evaluated|quality_report.json" services tests
```

Expected: run writeback and scenario aggregation are present.

- [ ] **Step 3: Commit verification fixes if needed**

```powershell
git add schemas/quality_gate.py services/artifact_evaluation_service.py services/quality_gate_service.py services/agent_run_service.py services/scenario_run_service.py tests/test_artifact_evaluation_service.py tests/test_quality_gate_service.py tests/test_agent_run_service_enhancements.py tests/test_scenario_run_service.py
git commit -m "test: lock gpkg quality gate"
```

## Self-Review

- GPKG is readable by the evaluator.
- Quality gate produces machine-readable reports.
- Run success can be rejected by quality checks.
- Scenario summaries aggregate child quality evidence.
