# Quality Policy And Spatial Metrics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Prefer `gpt-5.5` workers. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `QualityGateService` from a fixed format-level checker into a policy-driven quality gate with first-class spatial quality metrics for duplicate geometry, invalid geometry, source contribution balance, and coverage/feature retention evidence.

**Architecture:** Keep the existing `QualityGateReport` and `AgentRunService` quality gate call path stable. Add policy schemas and a loader that selects a default policy by task kind or an explicit `quality_policy_id`. Extend vector evaluation with deterministic spatial metrics. `QualityGateService.evaluate()` applies policy checks and thresholds, then records both metrics and decisions in `quality_report.json`.

**Tech Stack:** Python, Pydantic v2, GeoPandas, Shapely, pytest, existing `evaluate_vector_artifact()`, `QualityGateService`, `QualityGateReport`, `TaskKind`, `AgentRunService`, and scenario quality aggregation.

---

## Phase 0: Documentation Discovery

### Sources Consulted

- `services/quality_gate_service.py`
  - Current checks are `readable`, `non_empty`, `required_fields`, `geometry_type`, `aoi_intersection`, `source_lineage`, and `multi_source_lineage`.
- `services/artifact_evaluation_service.py`
  - Current vector metrics include feature count, CRS, geometry types, missing fields, bbox, AOI consistency, total polygon area, and total line length.
- `schemas/quality_gate.py`
  - `QualityGateReport` already supports `checks`, `metrics`, and `failure_reasons` dictionaries.
- `services/agent_run_service.py`
  - Writes `output/quality_report.json`, emits `quality_gate_evaluated`, and rejects unaccepted GPKG outputs.
- `services/scenario_run_service.py`
  - Aggregates child quality evidence into scenario summaries.
- `tests/test_quality_gate_service.py`
  - Existing tests cover multisource building acceptance and geometry type rejection.
- `tests/test_artifact_evaluation_service.py`
  - Existing fixtures write polygon, line, and GPKG artifacts.

### Allowed APIs

- Use GeoPandas `read_file()`.
- Use Shapely geometry properties such as `is_valid`, `wkb`, `area`, and `length`.
- Keep `QualityGateReport` compatible by adding optional fields rather than removing existing ones.
- Keep current checks available as the default policy.
- Allow policy selection by `quality_policy_id`, with a task-kind default fallback.

### Anti-Pattern Guards

- Do not make golden-data precision or recall mandatory in this slice.
- Do not reject sparse POI or water outputs solely because they do not fill the AOI.
- Do not compute pairwise near-duplicate metrics for large outputs in this first slice.
- Do not bypass `quality_report.json` or the existing audit event.
- Do not remove compatibility zip packaging.

## File Structure

- Create: `schemas/quality_policy.py`
- Create: `services/quality_policy_service.py`
- Modify: `services/artifact_evaluation_service.py`
- Modify: `services/quality_gate_service.py`
- Modify: `schemas/quality_gate.py`
- Modify: `services/agent_run_service.py`
- Test: `tests/test_quality_policy_service.py`
- Test: `tests/test_artifact_evaluation_service.py`
- Test: `tests/test_quality_gate_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`

---

### Task 1: Add Quality Policy Schemas And Defaults

**Files:**
- Create: `schemas/quality_policy.py`
- Create: `services/quality_policy_service.py`
- Test: `tests/test_quality_policy_service.py`

- [ ] **Step 1: Write failing schema and default policy tests**

Create `tests/test_quality_policy_service.py`:

```python
from __future__ import annotations

from schemas.task_kind import TaskKind
from services.quality_policy_service import get_quality_policy


def test_default_building_quality_policy_contains_spatial_checks() -> None:
    policy = get_quality_policy(task_kind=TaskKind.building, policy_id=None)

    check_ids = [check.check_id for check in policy.checks]

    assert policy.policy_id == "quality.default.building.v1"
    assert "duplicate_geometry_rate" in check_ids
    assert "invalid_geometry_rate" in check_ids
    assert "source_contribution_balance" in check_ids
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_quality_policy_service.py -q
```

Expected: FAIL because the policy service does not exist.

- [ ] **Step 3: Implement quality policy schema**

Create `schemas/quality_policy.py`:

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from schemas.task_kind import TaskKind


class QualityPolicyCheck(BaseModel):
    check_id: str
    metric_name: str
    severity: str = "hard"
    operator: str = "lte"
    threshold: float | int | bool | str | None = None
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class QualityPolicy(BaseModel):
    policy_id: str
    task_kind: TaskKind
    description: str = ""
    checks: list[QualityPolicyCheck] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Implement default policy service**

Create `services/quality_policy_service.py` with deterministic in-code defaults for:

- `quality.default.building.v1`
- `quality.default.road.v1`
- `quality.default.water_polygon.v1`
- `quality.default.waterways.v1`
- `quality.default.poi.v1`

Include current checks and new spatial checks:

- `duplicate_geometry_rate`
- `invalid_geometry_rate`
- `source_contribution_balance`
- `feature_retention_rate`, soft severity
- `coverage_retention_rate`, soft severity

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_quality_policy_service.py -q
git add schemas/quality_policy.py services/quality_policy_service.py tests/test_quality_policy_service.py
git commit -m "feat: add default quality policies"
```

### Task 2: Extend Vector Evaluation With Spatial Metrics

**Files:**
- Modify: `services/artifact_evaluation_service.py`
- Test: `tests/test_artifact_evaluation_service.py`

- [ ] **Step 1: Add failing spatial metric tests**

Append:

```python
def test_evaluate_vector_artifact_reports_duplicate_and_invalid_geometry_rates(tmp_path):
    path = tmp_path / "quality.gpkg"
    polygon = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    invalid = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])
    frame = gpd.GeoDataFrame(
        {"source_id": ["a", "a", "b"]},
        geometry=[polygon, polygon, invalid],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    metrics = evaluate_vector_artifact(path, required_fields=["geometry", "source_id"])

    assert metrics["duplicate_geometry_rate"] > 0
    assert metrics["invalid_geometry_rate"] > 0
    assert metrics["source_feature_counts"] == {"a": 2, "b": 1}
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_artifact_evaluation_service.py::test_evaluate_vector_artifact_reports_duplicate_and_invalid_geometry_rates -q
```

Expected: FAIL because the new metrics are missing.

- [ ] **Step 3: Implement metrics**

In `services/artifact_evaluation_service.py`, add helper functions:

```python
def _geometry_quality_metrics(frame: gpd.GeoDataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "duplicate_geometry_rate": 0.0,
            "invalid_geometry_rate": 0.0,
            "source_feature_counts": {},
            "source_contribution_balance": 0.0,
        }
    geometries = [geom for geom in frame.geometry if geom is not None]
    total = len(geometries)
    duplicate_count = total - len({geom.wkb_hex for geom in geometries})
    invalid_count = sum(1 for geom in geometries if not geom.is_valid)
    source_counts = _source_feature_counts(frame)
    return {
        "duplicate_geometry_rate": duplicate_count / total if total else 0.0,
        "invalid_geometry_rate": invalid_count / total if total else 0.0,
        "source_feature_counts": source_counts,
        "source_contribution_balance": _gini(list(source_counts.values())),
    }
```

Use exact WKB duplicate detection only. Add `_source_feature_counts()` and `_gini()` helpers. Update `evaluate_vector_artifact()` to merge the new metrics.

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_artifact_evaluation_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/artifact_evaluation_service.py tests/test_artifact_evaluation_service.py
git commit -m "feat: measure spatial artifact quality"
```

### Task 3: Apply Policy Checks In Quality Gate

**Files:**
- Modify: `schemas/quality_gate.py`
- Modify: `services/quality_gate_service.py`
- Test: `tests/test_quality_gate_service.py`

- [ ] **Step 1: Add failing policy enforcement tests**

Append to `tests/test_quality_gate_service.py`:

```python
def test_quality_gate_rejects_duplicate_geometry_above_policy_threshold(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.gpkg"
    polygon = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    frame = gpd.GeoDataFrame(
        {"source_id": ["raw.osm.building", "raw.microsoft.building"]},
        geometry=[polygon, polygon],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    report = QualityGateService().evaluate(
        artifact_path=path,
        task_kind=TaskKind.building,
        required_fields=["geometry", "source_id"],
        requested_bbox=(-1, -1, 2, 2),
        component_coverage={
            "raw.osm.building": {"feature_count": 1, "coverage_status": "available"},
            "raw.microsoft.building": {"feature_count": 1, "coverage_status": "available"},
        },
        quality_policy_id="quality.default.building.v1",
    )

    assert report.accepted is False
    assert report.policy_id == "quality.default.building.v1"
    assert "duplicate_geometry_rate" in report.failure_reasons
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_quality_gate_service.py::test_quality_gate_rejects_duplicate_geometry_above_policy_threshold -q
```

Expected: FAIL because policy selection and spatial checks are not wired.

- [ ] **Step 3: Extend report schema**

Add optional fields to `schemas/quality_gate.py`:

```python
policy_id: str | None = None
soft_failure_reasons: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Apply policy checks**

In `QualityGateService.evaluate()`:

- add parameter `quality_policy_id: str | None = None`
- load policy with `get_quality_policy(task_kind=task_kind, policy_id=quality_policy_id)`
- keep legacy checks as explicit checks in the policy path
- evaluate numeric operators `lte`, `lt`, `gte`, `gt`, `eq`
- hard check failures reject
- soft check failures populate `soft_failure_reasons` but do not reject

Preserve old check keys so existing tests continue to pass.

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_quality_gate_service.py tests/test_quality_policy_service.py tests/test_artifact_evaluation_service.py -q
git add schemas/quality_gate.py services/quality_gate_service.py tests/test_quality_gate_service.py
git commit -m "feat: apply policy driven quality gates"
```

### Task 4: Pass Policy IDs Through Runs And Scenarios

**Files:**
- Modify: `services/agent_run_service.py`
- Modify: `services/scenario_run_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`
- Test: `tests/test_scenario_run_service.py`

- [ ] **Step 1: Add failing run propagation test**

Add or update a focused test in `tests/test_agent_run_service_enhancements.py` that:

- creates a plan with `plan.context["quality_policy_id"] = "quality.default.building.v1"`
- runs writeback against a GPKG
- asserts `output/quality_report.json` contains `"policy_id": "quality.default.building.v1"`

- [ ] **Step 2: Add failing scenario aggregation test**

Update `tests/test_scenario_run_service.py` to assert scenario quality summary includes per-child `policy_id` values when child quality reports include them.

- [ ] **Step 3: Wire agent run policy extraction**

In `AgentRunService._writeback_artifact()` or the nearest quality gate call site, extract policy id from:

1. `plan.context["quality_policy_id"]`
2. `plan.context["intent"]["quality_policy_id"]`
3. request metadata if available in the existing request model

Pass it to `QualityGateService.evaluate()`.

- [ ] **Step 4: Wire scenario policy metadata**

Ensure scenario metadata `quality_policy_id` from the validation matrix is passed into child run planning context or is visible to the quality gate through the child request. Use the smallest existing metadata path; do not add a new public API field if request metadata already carries it.

- [ ] **Step 5: Verify and commit**

```powershell
py -3.13 -m pytest tests/test_agent_run_service_enhancements.py tests/test_scenario_run_service.py tests/test_quality_gate_service.py -q
git add services/agent_run_service.py services/scenario_run_service.py tests/test_agent_run_service_enhancements.py tests/test_scenario_run_service.py
git commit -m "feat: propagate quality policy evidence"
```

### Task 5: Document Policy Levels And Future Golden Metrics

**Files:**
- Modify: `docs/no-ui-agent-operations.md`
- Modify: `docs/v2-operations.md`
- Test: `tests/test_no_ui_operations_docs.py`

- [ ] **Step 1: Add failing docs test**

Update `tests/test_no_ui_operations_docs.py`:

```python
def test_no_ui_runbook_documents_quality_policy_outputs() -> None:
    text = Path("docs/no-ui-agent-operations.md").read_text(encoding="utf-8")

    assert "quality_policy_id" in text
    assert "duplicate_geometry_rate" in text
    assert "invalid_geometry_rate" in text
    assert "source_contribution_balance" in text
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_no_ui_operations_docs.py::test_no_ui_runbook_documents_quality_policy_outputs -q
```

Expected: FAIL because the new policy docs are missing.

- [ ] **Step 3: Update docs**

Document:

- default policy by task kind
- hard checks versus soft checks
- first spatial metrics
- golden precision/recall and IoU as future policy checks, not required in this slice

- [ ] **Step 4: Run verification**

```powershell
py -3.13 -m pytest tests/test_no_ui_operations_docs.py tests/test_quality_gate_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add docs/no-ui-agent-operations.md docs/v2-operations.md tests/test_no_ui_operations_docs.py
git commit -m "docs: document quality policy metrics"
```

---

## Final Verification

Run:

```powershell
py -3.13 -m pytest tests/test_quality_policy_service.py tests/test_quality_gate_service.py tests/test_artifact_evaluation_service.py tests/test_agent_run_service_enhancements.py tests/test_scenario_run_service.py tests/test_no_ui_operations_docs.py -q
rg -n "quality_policy_id|duplicate_geometry_rate|invalid_geometry_rate|source_contribution_balance" schemas services tests docs
```

Expected:

- Focused tests pass.
- `quality_report.json` includes `policy_id`, hard failures, soft failures, and metrics.
- Scenario summaries preserve child quality policy evidence.

## Integration Commit

After all tasks pass:

```powershell
git status --short
git log --oneline -5
```

Then merge and push according to the active superpowers branch-finishing workflow.
