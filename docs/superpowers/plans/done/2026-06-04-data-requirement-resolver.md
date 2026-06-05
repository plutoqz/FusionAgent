# Data Requirement Resolver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Prefer `gpt-5.5` workers. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make source selection algorithm-driven by introducing an explicit data requirement resolver that maps task kind and selected workflow plan to required source roles, acceptable candidates, fallback order, and completeness policy.

**Architecture:** The Mission Compiler decides scope, the planner still selects algorithm/pattern, and the new Data Requirement Resolver reads the selected `WorkflowPlan` plus `TaskKind` to produce role-level source requirements. This first implementation is deterministic and table-driven, using existing KG/source ids. Source materialization behavior is not changed in this plan; later plans consume the resolver output.

**Tech Stack:** Python, Pydantic v2, pytest, existing `WorkflowPlan`, `ScenarioChildRunSpec`, `TaskKind`, `kg/source_catalog.py`, and planner context.

---

## Phase 0: Documentation Discovery

### Sources Consulted

- `docs/superpowers/specs/2026-06-03-engineering-agent-upgrade-design.md`
  - Requires algorithm-driven source roles, not global source priority.
- `schemas/task_kind.py`
  - Internal execution task vocabulary exists: `building`, `road`, `water_polygon`, `waterways`, `poi`.
- `schemas/agent.py`
  - `WorkflowPlan`, `WorkflowTask`, and `RunCreateRequest.preferred_pattern_id` already exist.
- `kg/source_catalog.py`
  - Existing source ids include OSM, Google, Microsoft, Overture, HydroRIVERS, HydroLAKES, GNS, Pakistan local waterways.
- `services/agent_run_service.py`
  - `_resolve_execution_inputs()` currently follows planner source candidates and calls `InputAcquisitionService`.
- `tests/test_planner_context.py`
  - Existing pattern for checking planner context enrichment.
- `tests/test_mission_compiler_service.py`
  - Existing task kind expectations.

### Allowed APIs

- Use `WorkflowPlan.tasks[*].algorithm_id`, `input.data_source_id`, and `output.data_type_id`.
- Use `TaskKind` to distinguish `water_polygon` from `waterways`.
- Store resolver evidence in `plan.context["data_requirements"]` or an audit event, but do not mutate public `JobType`.
- Use existing source ids from `kg/source_catalog.py`.

### Anti-Pattern Guards

- Do not hardcode `OSM > Google > Microsoft` as the first decision rule.
- Do not change `JobType`.
- Do not change the planner's selected algorithm in this slice.
- Do not add remote provider behavior here.
- Do not require height signals unless plan/mission explicitly asks for height.

## File Structure

- Create: `schemas/data_requirement.py`
  - Defines `SourceRoleRequirement`, `SourceCandidate`, and `DataRequirementPlan`.
- Create: `services/data_requirement_resolver_service.py`
  - Maps task kind and plan to role requirements.
- Modify: `services/scenario_run_service.py`
  - Carries task kind metadata already present; this plan only needs tests if scenario summaries include resolver evidence later.
- Modify: `services/agent_run_service.py`
  - Writes `data_requirements.json` and emits a `data_requirements_resolved` audit event before input materialization.
- Test: `tests/test_data_requirement_resolver_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`

---

### Task 1: Add Data Requirement Schemas

**Files:**
- Create: `schemas/data_requirement.py`
- Test: `tests/test_data_requirement_resolver_service.py`

- [ ] **Step 1: Write failing schema tests**

Create `tests/test_data_requirement_resolver_service.py` with the first test:

```python
from __future__ import annotations

from schemas.data_requirement import CompletenessPolicy, SourceCandidate, SourceRoleRequirement


def test_source_role_requirement_serializes_candidate_order() -> None:
    requirement = SourceRoleRequirement(
        role_id="primary_footprint",
        required=True,
        geometry_types=["Polygon", "MultiPolygon"],
        completeness_policy=CompletenessPolicy.required_non_empty,
        candidates=[
            SourceCandidate(source_id="raw.osm.building", provider_family="osm", priority=10),
            SourceCandidate(source_id="raw.microsoft.building", provider_family="microsoft", priority=20),
        ],
    )

    payload = requirement.model_dump(mode="json")

    assert payload["role_id"] == "primary_footprint"
    assert payload["completeness_policy"] == "required_non_empty"
    assert [item["source_id"] for item in payload["candidates"]] == [
        "raw.osm.building",
        "raw.microsoft.building",
    ]
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_data_requirement_resolver_service.py::test_source_role_requirement_serializes_candidate_order -q
```

Expected: FAIL because `schemas.data_requirement` does not exist.

- [ ] **Step 3: Implement schemas**

Create `schemas/data_requirement.py`:

```python
from __future__ import annotations

from enum import Enum
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from schemas.task_kind import TaskKind


class CompletenessPolicy(str, Enum):
    required_non_empty = "required_non_empty"
    required_query_with_sparse_allowed = "required_query_with_sparse_allowed"
    optional_reference = "optional_reference"
    optional_when_requirement_absent = "optional_when_requirement_absent"


class SourceCandidate(BaseModel):
    source_id: str
    provider_family: str
    priority: int
    role: Optional[str] = None
    requires_auth: bool = False
    materialization_scope: str = "aoi"
    notes: List[str] = Field(default_factory=list)


class SourceRoleRequirement(BaseModel):
    role_id: str
    required: bool = True
    geometry_types: List[str] = Field(default_factory=list)
    completeness_policy: CompletenessPolicy
    candidates: List[SourceCandidate] = Field(default_factory=list)
    fallback_role_ids: List[str] = Field(default_factory=list)


class DataRequirementPlan(BaseModel):
    task_kind: TaskKind
    task_family: str
    algorithm_id: Optional[str] = None
    output_data_type: Optional[str] = None
    roles: List[SourceRoleRequirement] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_data_requirement_resolver_service.py::test_source_role_requirement_serializes_candidate_order -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add schemas/data_requirement.py tests/test_data_requirement_resolver_service.py
git commit -m "feat: add data requirement schemas"
```

### Task 2: Implement Deterministic Resolver

**Files:**
- Create: `services/data_requirement_resolver_service.py`
- Test: `tests/test_data_requirement_resolver_service.py`

- [ ] **Step 1: Add failing resolver tests**

Append:

```python
from schemas.agent import RunTrigger, RunTriggerType, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from schemas.task_kind import TaskKind
from services.data_requirement_resolver_service import DataRequirementResolverService


def _plan(*, algorithm_id: str, output_type: str) -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id="wf-test",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="test"),
        context={"retrieval": {"candidate_patterns": [{"pattern_id": "wp.test"}]}},
        tasks=[
            WorkflowTask(
                step=1,
                name="fusion",
                description="fusion",
                algorithm_id=algorithm_id,
                input=WorkflowTaskInput(data_type_id="dt.input", data_source_id="catalog.test"),
                output=WorkflowTaskOutput(data_type_id=output_type),
                kg_validated=True,
            )
        ],
        expected_output="out",
    )


def test_resolver_building_without_height_uses_footprint_roles() -> None:
    result = DataRequirementResolverService().resolve(
        task_kind=TaskKind.building,
        plan=_plan(algorithm_id="algo.fusion.building.v1", output_type="dt.building.fused"),
        mission_requirements={},
    )

    assert [role.role_id for role in result.roles] == ["primary_footprint", "reference_footprint"]
    primary = result.roles[0]
    assert [candidate.source_id for candidate in primary.candidates] == [
        "raw.osm.building",
        "raw.google.building",
        "raw.microsoft.building",
    ]
    assert all(role.completeness_policy.value == "required_non_empty" for role in result.roles)


def test_resolver_building_height_adds_height_signal_role_only_when_requested() -> None:
    result = DataRequirementResolverService().resolve(
        task_kind=TaskKind.building,
        plan=_plan(algorithm_id="algo.fusion.building.height_enriched.v1", output_type="dt.building.fused"),
        mission_requirements={"building_height": True},
    )

    assert [role.role_id for role in result.roles] == [
        "primary_footprint",
        "reference_footprint",
        "height_signal",
    ]
    assert result.roles[2].completeness_policy.value == "optional_when_requirement_absent"


def test_resolver_distinguishes_water_polygon_and_waterways() -> None:
    resolver = DataRequirementResolverService()

    polygon = resolver.resolve(
        task_kind=TaskKind.water_polygon,
        plan=_plan(algorithm_id="algo.fusion.water_polygon.priority_merge.v2", output_type="dt.water.fused"),
    )
    waterways = resolver.resolve(
        task_kind=TaskKind.waterways,
        plan=_plan(algorithm_id="algo.fusion.waterways.conflation.v7", output_type="dt.waterways.fused"),
    )

    assert polygon.roles[0].geometry_types == ["Polygon", "MultiPolygon"]
    assert waterways.roles[0].geometry_types == ["LineString", "MultiLineString"]
    assert "raw.hydrolakes.water" in [candidate.source_id for candidate in polygon.roles[1].candidates]
    assert "raw.hydrorivers.water" in [candidate.source_id for candidate in waterways.roles[1].candidates]
```

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_data_requirement_resolver_service.py -q
```

Expected: FAIL because resolver service does not exist.

- [ ] **Step 3: Implement resolver**

Create `services/data_requirement_resolver_service.py`:

```python
from __future__ import annotations

from typing import Any

from schemas.agent import WorkflowPlan
from schemas.data_requirement import CompletenessPolicy, DataRequirementPlan, SourceCandidate, SourceRoleRequirement
from schemas.task_kind import TaskKind, task_kind_family


class DataRequirementResolverService:
    def resolve(
        self,
        *,
        task_kind: TaskKind,
        plan: WorkflowPlan,
        mission_requirements: dict[str, Any] | None = None,
    ) -> DataRequirementPlan:
        algorithm_id = _selected_algorithm_id(plan)
        output_data_type = _selected_output_type(plan)
        mission_requirements = dict(mission_requirements or {})
        roles = _ROLE_BUILDERS[task_kind](mission_requirements, algorithm_id)
        return DataRequirementPlan(
            task_kind=task_kind,
            task_family=task_kind_family(task_kind),
            algorithm_id=algorithm_id,
            output_data_type=output_data_type,
            roles=roles,
            evidence={
                "resolver_version": "2026-06-04.v1",
                "basis": "task_kind_and_selected_algorithm",
                "workflow_id": plan.workflow_id,
            },
        )


def _selected_algorithm_id(plan: WorkflowPlan) -> str | None:
    for task in plan.tasks:
        if not task.is_transform:
            return task.algorithm_id
    return None


def _selected_output_type(plan: WorkflowPlan) -> str | None:
    for task in plan.tasks:
        if not task.is_transform:
            return task.output.data_type_id
    return None


def _candidate(source_id: str, provider_family: str, priority: int) -> SourceCandidate:
    return SourceCandidate(source_id=source_id, provider_family=provider_family, priority=priority)


def _building_roles(requirements: dict[str, Any], algorithm_id: str | None) -> list[SourceRoleRequirement]:
    roles = [
        SourceRoleRequirement(
            role_id="primary_footprint",
            geometry_types=["Polygon", "MultiPolygon"],
            completeness_policy=CompletenessPolicy.required_non_empty,
            candidates=[
                _candidate("raw.osm.building", "osm", 10),
                _candidate("raw.google.building", "google", 20),
                _candidate("raw.microsoft.building", "microsoft", 30),
            ],
        ),
        SourceRoleRequirement(
            role_id="reference_footprint",
            geometry_types=["Polygon", "MultiPolygon"],
            completeness_policy=CompletenessPolicy.required_non_empty,
            candidates=[
                _candidate("raw.microsoft.building", "microsoft", 10),
                _candidate("raw.google.building", "google", 20),
                _candidate("raw.osm.building", "osm", 30),
            ],
        ),
    ]
    wants_height = bool(requirements.get("building_height")) or "height" in str(algorithm_id or "").casefold()
    if wants_height:
        roles.append(
            SourceRoleRequirement(
                role_id="height_signal",
                required=True,
                geometry_types=["Raster", "Polygon", "MultiPolygon"],
                completeness_policy=CompletenessPolicy.optional_when_requirement_absent,
                candidates=[
                    _candidate("raw.local.building_height.raster", "local", 10),
                    _candidate("raw.google.building_3d", "google", 20),
                ],
            )
        )
    return roles


def _road_roles(_requirements: dict[str, Any], _algorithm_id: str | None) -> list[SourceRoleRequirement]:
    return [
        SourceRoleRequirement(
            role_id="base_network",
            geometry_types=["LineString", "MultiLineString"],
            completeness_policy=CompletenessPolicy.required_non_empty,
            candidates=[_candidate("raw.osm.road", "osm", 10)],
        ),
        SourceRoleRequirement(
            role_id="reference_network",
            geometry_types=["LineString", "MultiLineString"],
            completeness_policy=CompletenessPolicy.optional_reference,
            candidates=[
                _candidate("raw.overture.transportation", "overture", 10),
                _candidate("raw.overture.road", "overture", 20),
            ],
        ),
    ]


def _water_polygon_roles(_requirements: dict[str, Any], _algorithm_id: str | None) -> list[SourceRoleRequirement]:
    return [
        SourceRoleRequirement(
            role_id="base_water_polygon",
            geometry_types=["Polygon", "MultiPolygon"],
            completeness_policy=CompletenessPolicy.required_query_with_sparse_allowed,
            candidates=[_candidate("raw.osm.water", "osm", 10)],
        ),
        SourceRoleRequirement(
            role_id="reference_water_polygon",
            geometry_types=["Polygon", "MultiPolygon"],
            completeness_policy=CompletenessPolicy.optional_reference,
            candidates=[_candidate("raw.hydrolakes.water", "hydrosheds", 10)],
        ),
    ]


def _waterways_roles(_requirements: dict[str, Any], _algorithm_id: str | None) -> list[SourceRoleRequirement]:
    return [
        SourceRoleRequirement(
            role_id="base_waterway_line",
            geometry_types=["LineString", "MultiLineString"],
            completeness_policy=CompletenessPolicy.required_query_with_sparse_allowed,
            candidates=[_candidate("raw.osm.waterways", "osm", 10)],
        ),
        SourceRoleRequirement(
            role_id="reference_river_line",
            geometry_types=["LineString", "MultiLineString"],
            completeness_policy=CompletenessPolicy.optional_reference,
            candidates=[
                _candidate("raw.hydrorivers.water", "hydrosheds", 10),
                _candidate("raw.local.pakistan.waterways", "local", 20),
            ],
        ),
    ]


def _poi_roles(_requirements: dict[str, Any], _algorithm_id: str | None) -> list[SourceRoleRequirement]:
    return [
        SourceRoleRequirement(
            role_id="base_poi",
            geometry_types=["Point", "MultiPoint"],
            completeness_policy=CompletenessPolicy.required_query_with_sparse_allowed,
            candidates=[_candidate("raw.osm.poi", "osm", 10)],
        ),
        SourceRoleRequirement(
            role_id="reference_poi",
            geometry_types=["Point", "MultiPoint"],
            completeness_policy=CompletenessPolicy.optional_reference,
            candidates=[_candidate("raw.gns.poi", "gns", 10)],
        ),
    ]


_ROLE_BUILDERS = {
    TaskKind.building: _building_roles,
    TaskKind.road: _road_roles,
    TaskKind.water_polygon: _water_polygon_roles,
    TaskKind.waterways: _waterways_roles,
    TaskKind.poi: _poi_roles,
}
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_data_requirement_resolver_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add schemas/data_requirement.py services/data_requirement_resolver_service.py tests/test_data_requirement_resolver_service.py
git commit -m "feat: resolve task data requirements"
```

### Task 3: Persist Resolver Evidence During Runs

**Files:**
- Modify: `services/agent_run_service.py`
- Test: `tests/test_agent_run_service_enhancements.py`

- [ ] **Step 1: Add failing run evidence test**

In `tests/test_agent_run_service_enhancements.py`, add a test near other task-driven auto tests:

```python
def test_agent_run_service_writes_data_requirements_before_materialization(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    captured: dict[str, object] = {}

    def fake_resolve_task_driven_inputs(**kwargs):
        data_requirements_path = Path(kwargs["input_dir"]) / "data_requirements.json"
        captured["exists_before_materialization"] = data_requirements_path.exists()
        raise ValueError("stop after requirement evidence")

    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", fake_resolve_task_driven_inputs)

    with pytest.raises(ValueError):
        service.create_run(
            request=_build_auto_request(
                spatial_extent="Nairobi, Kenya",
                job_type=JobType.building,
                content="need building data for Nairobi",
            ),
            osm_zip_name=None,
            osm_zip_bytes=None,
            ref_zip_name=None,
            ref_zip_bytes=None,
        )

    assert captured["exists_before_materialization"] is True
```

`_build_auto_request()` already exists near the task-driven auto tests in this file and returns a `RunCreateRequest` with `input_strategy=RunInputStrategy.task_driven_auto`.

- [ ] **Step 2: Run and confirm failure**

```powershell
py -3.13 -m pytest tests/test_agent_run_service_enhancements.py::test_agent_run_service_writes_data_requirements_before_materialization -q
```

Expected: FAIL because no `data_requirements.json` is written.

- [ ] **Step 3: Implement evidence write**

In `services/agent_run_service.py`, import:

```python
from schemas.task_kind import TaskKind, expand_job_type_to_task_kinds
from services.data_requirement_resolver_service import DataRequirementResolverService
```

Add `self.data_requirement_resolver = DataRequirementResolverService()` in `AgentRunService.__init__`.

Before the first call to `resolve_task_driven_inputs()` in `_resolve_execution_inputs()`, compute:

```python
task_kind = _task_kind_for_request(request)
requirements = self.data_requirement_resolver.resolve(task_kind=task_kind, plan=plan)
requirements_path = input_dir / "data_requirements.json"
requirements_path.write_text(
    json.dumps(requirements.model_dump(mode="json"), ensure_ascii=False, indent=2),
    encoding="utf-8",
)
self._update_status(
    run_id,
    RunPhase.running,
    progress=35,
    plan_revision=self._extract_plan_revision(plan),
    checkpoint=self._checkpoint(stage="input_resolution", plan_revision=self._extract_plan_revision(plan)),
    event_kind="data_requirements_resolved",
    event_message="Data source role requirements resolved.",
    event_details={
        "path": str(requirements_path),
        "task_kind": requirements.task_kind.value,
        "role_ids": [role.role_id for role in requirements.roles],
    },
)
```

Add helper:

```python
def _task_kind_for_request(request: RunCreateRequest) -> TaskKind:
    preferred = str(request.preferred_pattern_id or "")
    if "waterways" in preferred:
        return TaskKind.waterways
    if "water_polygon" in preferred:
        return TaskKind.water_polygon
    expanded = expand_job_type_to_task_kinds(request.job_type)
    return expanded[0]
```

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_data_requirement_resolver_service.py tests/test_agent_run_service_enhancements.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add services/agent_run_service.py tests/test_agent_run_service_enhancements.py
git commit -m "feat: record data requirement evidence"
```

### Task 4: Add Planner Context Hook Without Changing Selection

**Files:**
- Modify: `agent/planner.py` or the actual planner context builder file if context construction lives elsewhere
- Test: `tests/test_planner_context.py`

- [ ] **Step 1: Locate actual planner context builder**

Run:

```powershell
rg -n "class .*Context|preferred_pattern_id_override|candidate_patterns|data_sources" agent services tests/test_planner_context.py
```

Expected: identify the existing context builder used by `AgentRunService`.

- [ ] **Step 2: Add failing context test**

In `tests/test_planner_context.py`, add:

```python
def test_planner_context_can_include_data_requirement_hint() -> None:
    context = build_planner_context_for_test(
        job_type=JobType.building,
        trigger_content="need building data",
        data_requirements={
            "task_kind": "building",
            "roles": [{"role_id": "primary_footprint"}, {"role_id": "reference_footprint"}],
        },
    )

    assert context["data_requirements"]["task_kind"] == "building"
    assert [role["role_id"] for role in context["data_requirements"]["roles"]] == [
        "primary_footprint",
        "reference_footprint",
    ]
```

Use the actual helper names in `tests/test_planner_context.py`; do not invent a new public planner API if an existing fixture can be extended.

- [ ] **Step 3: Implement only the context pass-through**

Add optional `data_requirements` support to the context builder and include it under:

```python
context["data_requirements"] = data_requirements
```

Do not change scoring or pattern selection in this plan.

- [ ] **Step 4: Verify**

```powershell
py -3.13 -m pytest tests/test_planner_context.py tests/test_data_requirement_resolver_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add agent services tests/test_planner_context.py
git commit -m "feat: expose data requirement hints in planner context"
```

### Task 5: Final Verification

- [ ] **Step 1: Focused tests**

```powershell
py -3.13 -m pytest tests/test_data_requirement_resolver_service.py tests/test_agent_run_service_enhancements.py tests/test_planner_context.py tests/test_mission_compiler_service.py tests/test_task_kind.py -q
```

Expected: PASS.

- [ ] **Step 2: Anti-pattern scans**

```powershell
rg -n "OSM > Google > Microsoft|osm.*google.*microsoft" services tests docs/superpowers/plans
```

Expected: no implementation comment claims a global priority rule; only role candidate tests may mention ordered candidates.

```powershell
rg -n "JobType\\.(waterways|water_polygon)" schemas services tests
```

Expected: no output.

- [ ] **Step 3: Commit verification fixes if any**

```powershell
git add schemas/data_requirement.py services/data_requirement_resolver_service.py services/agent_run_service.py tests/test_data_requirement_resolver_service.py tests/test_agent_run_service_enhancements.py tests/test_planner_context.py
git commit -m "test: lock data requirement resolver"
```

## Self-Review

- The resolver is algorithm/task-kind driven.
- Building height is conditional.
- Water polygon and waterways are separate.
- No materialization fallback behavior is changed yet.
