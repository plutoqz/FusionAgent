# Mission Compiler And TaskKind Water Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the first engineering upgrade slice: deterministic mission compilation, internal execution task kinds, and independent `water_polygon` / `waterways` scenario children while preserving the public `JobType` API.

**Architecture:** Keep `JobType` as the public run API (`building`, `road`, `water`, `poi`) and add a narrower internal `TaskKind` vocabulary for scenario execution. The Mission Compiler converts `ScenarioRunRequest` into child specs before `ScenarioRunService` starts runs; water task kinds route through existing `RunCreateRequest.preferred_pattern_id` and natural trigger hints so the current KG planner selects the already-seeded water polygon and waterways patterns.

**Tech Stack:** Python, Pydantic v2, pytest, existing KG seed/repository/planner/scenario services.

---

## Phase 0: Documentation Discovery

### Sources Consulted

- `docs/superpowers/specs/2026-06-03-engineering-agent-upgrade-design.md:13-23`, `:81-125`, `:415-445`
  - Confirms full disaster mission bundle, water split, `partial` semantics, and Phase 1/2 scope.
- `schemas/fusion.py:9-14`
  - `JobType` currently exposes `building`, `road`, `water`, `poi`.
- `schemas/scenario.py:19-39`
  - `ScenarioRunRequest` has `job_types`, metadata, AOI, CRS, debug fields.
  - `ScenarioChildRunSpec` currently only carries `job_type` and run parameters.
- `schemas/agent.py:217-225`
  - `RunCreateRequest` already supports `preferred_pattern_id`; use this instead of adding a new public run field in this first slice.
- `services/scenario_run_service.py:32-44`, `:255-308`, `:447-465`, `:592-600`
  - Child specs are built from `_scenario_job_types()`.
  - `_run_child()` passes `spec.job_type` to `RunCreateRequest`.
  - Flood/typhoon currently expand to building, road, water; earthquake expands to building, road.
  - Child summaries currently do not record execution task kind or family.
- `services/scenario_trigger_service.py:11-33`, `:52-66`
  - Trigger events parse `requested_layers` into `JobType`; default is currently building plus road.
- `kg/seed.py:1057-1134`
  - Existing KG patterns include `wp.flood.water.default`, `wp.flood.water_polygon.default`, and `wp.flood.waterways.default`.
- `kg/source_catalog.py:145-163`, `:330-385`
  - Existing catalog sources include `catalog.flood.water_polygon` and `catalog.flood.waterways`.
- `agent/retriever.py:359-363`, `:529-537`
  - Waterways preference is already inferred from trigger text and can choose `dt.waterways.fused`.
- `agent/tooling.py:60-70`
  - Registered tools already support `algo.fusion.water_polygon.priority_merge.v2` and `algo.fusion.waterways.conflation.v7`.
- `services/agent_run_service.py:952-960`
  - `AgentRunService` already forwards `request.preferred_pattern_id` into the planner context builder.
- `tests/test_scenario_run_service.py:43-57`, `:129-173`, `:247-283`
  - Current scenario tests expect 3 flood children and fake run IDs based on `JobType`, which must be updated for two water children.

### Allowed APIs

- Use `RunCreateRequest.preferred_pattern_id` to bias the planner to a KG pattern.
- Use `ScenarioRunRequest.metadata` to carry trigger-layer parsing evidence such as `requested_task_kinds` and `unsupported_requested_layers`.
- Use existing `ScenarioPhase.partial`; do not add a scenario-level `recovering` or `degraded` status.
- Use existing KG pattern ids:
  - `wp.flood.water_polygon.default`
  - `wp.flood.waterways.default`
  - `wp.generic.poi.default`
  - `wp.flood.road.default`
  - `wp.flood.building.default`
- Use existing task ids and output types:
  - `task.waterways.fusion`
  - `dt.waterways.bundle`
  - `dt.waterways.fused`
  - `dt.water.bundle`
  - `dt.water.fused`

### Anti-Pattern Guards

- Do not add `JobType.waterways` or `JobType.water_polygon` in this first slice.
- Do not select concrete algorithms in the Mission Compiler. It may attach a KG pattern hint only as a compatibility bridge to express the requested task kind to the current planner.
- Do not create one combined water child for the full disaster bundle.
- Do not use `job_type` alone as a child-run identity after this change; two children can both have `JobType.water`.
- Do not change data acquisition, GPKG output, quality gates, or failure recovery in this plan.

## File Structure

- Create: `schemas/task_kind.py`
  - Owns internal execution task vocabulary and deterministic mappings to public job type, task family, output type, and planner pattern hints.
- Create: `schemas/mission.py`
  - Owns `MissionTaskSpec` and `MissionSpec`, so Mission Compiler output is explicit and testable.
- Create: `services/mission_compiler_service.py`
  - Converts a `ScenarioRunRequest` or trigger `requested_layers` into a deterministic mission spec.
- Modify: `schemas/scenario.py`
  - Add optional child spec fields: `task_kind`, `task_family`, `preferred_pattern_id`, `output_data_type`.
- Modify: `services/scenario_run_service.py`
  - Replace `_scenario_job_types()` expansion with Mission Compiler.
  - Pass `preferred_pattern_id` to child `RunCreateRequest`.
  - Preserve task kind metadata in child result and scenario summary.
- Modify: `services/scenario_trigger_service.py`
  - Parse `requested_layers` into task kinds as well as compatibility `job_types`.
- Modify: `tests/test_scenario_run_service.py`
  - Update flood bundle expectations from 3 children to 5 executable task kinds.
  - Make fake run ids unique by task kind / preferred pattern.
- Modify: `tests/test_scenario_trigger_service.py`
  - Add water-family and disaster-default trigger normalization coverage.
- Create: `tests/test_task_kind.py`
  - Covers TaskKind mapping invariants.
- Create: `tests/test_mission_compiler_service.py`
  - Covers full disaster bundle, explicit single-family scope, water alias expansion, and unsupported layer recording.

---

### Task 1: Add Internal TaskKind Vocabulary

**Files:**
- Create: `schemas/task_kind.py`
- Test: `tests/test_task_kind.py`

- [ ] **Step 1: Write the failing TaskKind tests**

Create `tests/test_task_kind.py`:

```python
from __future__ import annotations

from schemas.fusion import JobType
from schemas.task_kind import (
    TaskKind,
    expand_job_type_to_task_kinds,
    normalize_task_kind,
    task_kind_family,
    task_kind_output_type,
    task_kind_preferred_pattern_id,
    task_kind_to_job_type,
)


def test_task_kind_maps_to_public_job_type_without_extending_job_type() -> None:
    assert task_kind_to_job_type(TaskKind.building) == JobType.building
    assert task_kind_to_job_type(TaskKind.road) == JobType.road
    assert task_kind_to_job_type(TaskKind.water_polygon) == JobType.water
    assert task_kind_to_job_type(TaskKind.waterways) == JobType.water
    assert task_kind_to_job_type(TaskKind.poi) == JobType.poi


def test_task_kind_records_product_family_and_output_type() -> None:
    assert task_kind_family(TaskKind.water_polygon) == "water"
    assert task_kind_family(TaskKind.waterways) == "water"
    assert task_kind_output_type(TaskKind.water_polygon) == "dt.water.fused"
    assert task_kind_output_type(TaskKind.waterways) == "dt.waterways.fused"


def test_water_job_type_expands_to_two_execution_task_kinds() -> None:
    assert expand_job_type_to_task_kinds(JobType.water) == [
        TaskKind.water_polygon,
        TaskKind.waterways,
    ]


def test_task_kind_pattern_hints_are_only_needed_for_water_split() -> None:
    assert task_kind_preferred_pattern_id(TaskKind.water_polygon, "flood") == "wp.flood.water_polygon.default"
    assert task_kind_preferred_pattern_id(TaskKind.waterways, "flood") == "wp.flood.waterways.default"
    assert task_kind_preferred_pattern_id(TaskKind.building, "flood") is None


def test_normalize_task_kind_accepts_aliases() -> None:
    assert normalize_task_kind("water") == [TaskKind.water_polygon, TaskKind.waterways]
    assert normalize_task_kind("water_polygon") == [TaskKind.water_polygon]
    assert normalize_task_kind("waterways") == [TaskKind.waterways]
    assert normalize_task_kind("river") == [TaskKind.waterways]
    assert normalize_task_kind("poi") == [TaskKind.poi]
```

- [ ] **Step 2: Run the new tests and confirm they fail**

Run:

```powershell
pytest tests/test_task_kind.py -q
```

Expected: FAIL because `schemas.task_kind` does not exist.

- [ ] **Step 3: Implement the TaskKind vocabulary**

Create `schemas/task_kind.py`:

```python
from __future__ import annotations

from enum import Enum

from schemas.fusion import JobType


class TaskKind(str, Enum):
    building = "building"
    road = "road"
    water_polygon = "water_polygon"
    waterways = "waterways"
    poi = "poi"


FULL_DISASTER_TASK_KINDS: tuple[TaskKind, ...] = (
    TaskKind.building,
    TaskKind.road,
    TaskKind.water_polygon,
    TaskKind.waterways,
    TaskKind.poi,
)

_TASK_KIND_JOB_TYPES: dict[TaskKind, JobType] = {
    TaskKind.building: JobType.building,
    TaskKind.road: JobType.road,
    TaskKind.water_polygon: JobType.water,
    TaskKind.waterways: JobType.water,
    TaskKind.poi: JobType.poi,
}

_TASK_KIND_FAMILIES: dict[TaskKind, str] = {
    TaskKind.building: "building",
    TaskKind.road: "road",
    TaskKind.water_polygon: "water",
    TaskKind.waterways: "water",
    TaskKind.poi: "poi",
}

_TASK_KIND_OUTPUT_TYPES: dict[TaskKind, str] = {
    TaskKind.building: "dt.building.fused",
    TaskKind.road: "dt.road.fused",
    TaskKind.water_polygon: "dt.water.fused",
    TaskKind.waterways: "dt.waterways.fused",
    TaskKind.poi: "dt.poi.fused",
}

_WATER_PATTERN_HINTS: dict[TaskKind, str] = {
    TaskKind.water_polygon: "wp.flood.water_polygon.default",
    TaskKind.waterways: "wp.flood.waterways.default",
}

_TASK_KIND_ALIASES: dict[str, tuple[TaskKind, ...]] = {
    "building": (TaskKind.building,),
    "buildings": (TaskKind.building,),
    "road": (TaskKind.road,),
    "roads": (TaskKind.road,),
    "water": (TaskKind.water_polygon, TaskKind.waterways),
    "water_polygon": (TaskKind.water_polygon,),
    "water-polygons": (TaskKind.water_polygon,),
    "waterbody": (TaskKind.water_polygon,),
    "waterbodies": (TaskKind.water_polygon,),
    "lake": (TaskKind.water_polygon,),
    "lakes": (TaskKind.water_polygon,),
    "waterways": (TaskKind.waterways,),
    "waterway": (TaskKind.waterways,),
    "river": (TaskKind.waterways,),
    "rivers": (TaskKind.waterways,),
    "stream": (TaskKind.waterways,),
    "canal": (TaskKind.waterways,),
    "poi": (TaskKind.poi,),
    "pois": (TaskKind.poi,),
    "point_of_interest": (TaskKind.poi,),
    "points_of_interest": (TaskKind.poi,),
}


def task_kind_to_job_type(task_kind: TaskKind) -> JobType:
    return _TASK_KIND_JOB_TYPES[task_kind]


def task_kind_family(task_kind: TaskKind) -> str:
    return _TASK_KIND_FAMILIES[task_kind]


def task_kind_output_type(task_kind: TaskKind) -> str:
    return _TASK_KIND_OUTPUT_TYPES[task_kind]


def task_kind_preferred_pattern_id(task_kind: TaskKind, disaster_type: str | None) -> str | None:
    if task_kind not in _WATER_PATTERN_HINTS:
        return None
    return _WATER_PATTERN_HINTS[task_kind]


def expand_job_type_to_task_kinds(job_type: JobType) -> list[TaskKind]:
    if job_type == JobType.water:
        return [TaskKind.water_polygon, TaskKind.waterways]
    return [TaskKind(job_type.value)]


def normalize_task_kind(value: object) -> list[TaskKind]:
    token = str(value or "").strip().casefold().replace(" ", "_")
    token = token.replace("-", "_")
    return list(_TASK_KIND_ALIASES.get(token, ()))
```

- [ ] **Step 4: Run TaskKind tests**

Run:

```powershell
pytest tests/test_task_kind.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add schemas/task_kind.py tests/test_task_kind.py
git commit -m "feat: add internal task kind vocabulary"
```

Expected: commit succeeds with only these two files staged.

### Task 2: Add Mission Compiler

**Files:**
- Create: `schemas/mission.py`
- Create: `services/mission_compiler_service.py`
- Test: `tests/test_mission_compiler_service.py`

- [ ] **Step 1: Write failing Mission Compiler tests**

Create `tests/test_mission_compiler_service.py`:

```python
from __future__ import annotations

from schemas.fusion import JobType
from schemas.scenario import ScenarioRunRequest
from schemas.task_kind import TaskKind
from services.mission_compiler_service import compile_scenario_mission, partition_requested_task_kinds


def test_disaster_scenario_without_explicit_layers_expands_to_full_bundle() -> None:
    request = ScenarioRunRequest(
        scenario_name="Karachi flood",
        trigger_content="Karachi, Pakistan has a flood disaster.",
        disaster_type="flood",
        spatial_extent="Karachi, Pakistan",
    )

    mission = compile_scenario_mission(request)

    assert [task.task_kind for task in mission.child_tasks] == [
        TaskKind.building,
        TaskKind.road,
        TaskKind.water_polygon,
        TaskKind.waterways,
        TaskKind.poi,
    ]
    assert [task.job_type for task in mission.child_tasks] == [
        JobType.building,
        JobType.road,
        JobType.water,
        JobType.water,
        JobType.poi,
    ]
    assert mission.task_families == ["building", "road", "water", "poi"]
    assert mission.scope_source == "default_disaster_bundle"


def test_explicit_building_scope_stays_single_task() -> None:
    request = ScenarioRunRequest(
        scenario_name="Nairobi building",
        trigger_content="only fuse building data for Nairobi",
        job_types=[JobType.building],
    )

    mission = compile_scenario_mission(request)

    assert [task.task_kind for task in mission.child_tasks] == [TaskKind.building]
    assert mission.scope_source == "explicit_job_types"


def test_explicit_water_family_expands_to_polygon_and_waterways() -> None:
    request = ScenarioRunRequest(
        scenario_name="Nairobi water",
        trigger_content="fuse water data for Nairobi",
        job_types=[JobType.water],
    )

    mission = compile_scenario_mission(request)

    assert [task.task_kind for task in mission.child_tasks] == [TaskKind.water_polygon, TaskKind.waterways]
    assert mission.child_tasks[0].preferred_pattern_id == "wp.flood.water_polygon.default"
    assert mission.child_tasks[1].preferred_pattern_id == "wp.flood.waterways.default"
    assert "water polygon" in mission.child_tasks[0].trigger_content
    assert "waterways" in mission.child_tasks[1].trigger_content


def test_requested_task_kind_metadata_can_select_waterways_only() -> None:
    request = ScenarioRunRequest(
        scenario_name="Pakistan waterways",
        trigger_content="fuse river data for Pakistan",
        metadata={"requested_task_kinds": ["waterways"]},
    )

    mission = compile_scenario_mission(request)

    assert [task.task_kind for task in mission.child_tasks] == [TaskKind.waterways]
    assert mission.child_tasks[0].job_type == JobType.water
    assert mission.child_tasks[0].output_data_type == "dt.waterways.fused"


def test_partition_requested_task_kinds_deduplicates_and_records_unsupported_layers() -> None:
    task_kinds, unsupported = partition_requested_task_kinds(["water", "river", "traffic"])

    assert task_kinds == [TaskKind.water_polygon, TaskKind.waterways]
    assert unsupported == ["traffic"]
```

- [ ] **Step 2: Run Mission Compiler tests and confirm they fail**

Run:

```powershell
pytest tests/test_mission_compiler_service.py -q
```

Expected: FAIL because `schemas.mission` and `services.mission_compiler_service` do not exist.

- [ ] **Step 3: Add mission schema models**

Create `schemas/mission.py`:

```python
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from schemas.fusion import JobType
from schemas.task_kind import TaskKind


class MissionTaskSpec(BaseModel):
    task_kind: TaskKind
    task_family: str
    job_type: JobType
    trigger_content: str
    disaster_type: Optional[str] = None
    spatial_extent: Optional[str] = None
    force_aoi_resolution: bool = False
    target_crs: Optional[str] = None
    debug: bool = False
    preferred_pattern_id: Optional[str] = None
    output_data_type: str


class MissionSpec(BaseModel):
    scope_source: str
    child_tasks: List[MissionTaskSpec] = Field(default_factory=list)
    task_families: List[str] = Field(default_factory=list)
    unsupported_layers: List[str] = Field(default_factory=list)
```

- [ ] **Step 4: Add Mission Compiler implementation**

Create `services/mission_compiler_service.py`:

```python
from __future__ import annotations

from typing import Any, Iterable

from schemas.fusion import JobType
from schemas.mission import MissionSpec, MissionTaskSpec
from schemas.scenario import ScenarioRunRequest
from schemas.task_kind import (
    FULL_DISASTER_TASK_KINDS,
    TaskKind,
    expand_job_type_to_task_kinds,
    normalize_task_kind,
    task_kind_family,
    task_kind_output_type,
    task_kind_preferred_pattern_id,
    task_kind_to_job_type,
)

_DISASTER_KEYWORDS = (
    "flood",
    "earthquake",
    "typhoon",
    "disaster",
    "emergency",
    "洪涝",
    "洪水",
    "内涝",
    "地震",
    "台风",
    "灾害",
    "应急",
)


def partition_requested_task_kinds(raw_layers: Any) -> tuple[list[TaskKind], list[str]]:
    task_kinds: list[TaskKind] = []
    unsupported_layers: list[str] = []
    layers = raw_layers if isinstance(raw_layers, list) else []
    for layer in layers:
        normalized = normalize_task_kind(layer)
        if not normalized:
            layer_text = str(layer).strip().lower()
            if layer_text and layer_text not in unsupported_layers:
                unsupported_layers.append(layer_text)
            continue
        for task_kind in normalized:
            if task_kind not in task_kinds:
                task_kinds.append(task_kind)
    return task_kinds, unsupported_layers


def compile_scenario_mission(request: ScenarioRunRequest) -> MissionSpec:
    task_kinds, scope_source = _resolve_task_kinds(request)
    child_tasks = [_build_task_spec(request, task_kind) for task_kind in task_kinds]
    task_families = _dedupe(task.task_family for task in child_tasks)
    unsupported = [
        str(item).strip().lower()
        for item in (request.metadata.get("unsupported_requested_layers") or [])
        if str(item).strip()
    ]
    return MissionSpec(
        scope_source=scope_source,
        child_tasks=child_tasks,
        task_families=task_families,
        unsupported_layers=unsupported,
    )


def _resolve_task_kinds(request: ScenarioRunRequest) -> tuple[list[TaskKind], str]:
    requested_task_kinds = request.metadata.get("requested_task_kinds")
    if isinstance(requested_task_kinds, list) and requested_task_kinds:
        task_kinds: list[TaskKind] = []
        for raw in requested_task_kinds:
            for task_kind in normalize_task_kind(raw):
                if task_kind not in task_kinds:
                    task_kinds.append(task_kind)
        if task_kinds:
            return task_kinds, "explicit_task_kinds"

    if request.job_types:
        task_kinds = []
        for job_type in request.job_types:
            for task_kind in expand_job_type_to_task_kinds(job_type):
                if task_kind not in task_kinds:
                    task_kinds.append(task_kind)
        return task_kinds, "explicit_job_types"

    if _is_disaster_scenario(request):
        return list(FULL_DISASTER_TASK_KINDS), "default_disaster_bundle"

    detected = _task_kinds_from_text(" ".join([request.scenario_name, request.trigger_content]))
    if detected:
        return detected, "detected_direct_task"

    return [TaskKind.building], "default_building"


def _is_disaster_scenario(request: ScenarioRunRequest) -> bool:
    if str(request.disaster_type or "").strip():
        return True
    text = " ".join([request.scenario_name, request.trigger_content]).casefold()
    return any(keyword in text for keyword in _DISASTER_KEYWORDS)


def _task_kinds_from_text(text: str) -> list[TaskKind]:
    found: list[TaskKind] = []
    lowered = text.casefold()
    for token in ("building", "road", "water", "waterways", "river", "poi"):
        if token not in lowered:
            continue
        for task_kind in normalize_task_kind(token):
            if task_kind not in found:
                found.append(task_kind)
    return found


def _build_task_spec(request: ScenarioRunRequest, task_kind: TaskKind) -> MissionTaskSpec:
    return MissionTaskSpec(
        task_kind=task_kind,
        task_family=task_kind_family(task_kind),
        job_type=task_kind_to_job_type(task_kind),
        trigger_content=_task_trigger_content(request.trigger_content, task_kind),
        disaster_type=request.disaster_type,
        spatial_extent=request.spatial_extent,
        force_aoi_resolution=request.force_aoi_resolution,
        target_crs=request.target_crs,
        debug=request.debug,
        preferred_pattern_id=task_kind_preferred_pattern_id(task_kind, request.disaster_type),
        output_data_type=task_kind_output_type(task_kind),
    )


def _task_trigger_content(base: str, task_kind: TaskKind) -> str:
    clean = str(base or "").strip()
    if task_kind == TaskKind.water_polygon:
        return f"{clean}; execute water polygon fusion only"
    if task_kind == TaskKind.waterways:
        return f"{clean}; execute waterways and river line fusion only"
    if task_kind == TaskKind.poi:
        return f"{clean}; execute bounded POI fusion"
    return clean


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
```

- [ ] **Step 5: Run Mission Compiler tests**

Run:

```powershell
pytest tests/test_mission_compiler_service.py tests/test_task_kind.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add schemas/mission.py services/mission_compiler_service.py tests/test_mission_compiler_service.py
git commit -m "feat: compile scenario missions into task kinds"
```

Expected: commit succeeds with only mission compiler files staged.

### Task 3: Wire TaskKind Into Scenario Child Runs

**Files:**
- Modify: `schemas/scenario.py`
- Modify: `services/scenario_run_service.py`
- Modify: `tests/test_scenario_run_service.py`

- [ ] **Step 1: Update failing scenario expectations**

In `tests/test_scenario_run_service.py`, update the implicit flood test to assert task kinds:

```python
from schemas.task_kind import TaskKind
```

Replace the assertion in `test_build_child_run_specs_expands_implicit_flood_bundle_for_chinese_scenario`:

```python
assert [spec.task_kind for spec in specs] == [
    TaskKind.building,
    TaskKind.road,
    TaskKind.water_polygon,
    TaskKind.waterways,
    TaskKind.poi,
]
assert [spec.job_type for spec in specs] == [
    JobType.building,
    JobType.road,
    JobType.water,
    JobType.water,
    JobType.poi,
]
assert specs[2].preferred_pattern_id == "wp.flood.water_polygon.default"
assert specs[3].preferred_pattern_id == "wp.flood.waterways.default"
assert all(spec.disaster_type == "flood" for spec in specs)
assert all(spec.spatial_extent == "Karachi, Pakistan" for spec in specs)
```

In `test_scenario_run_service_starts_all_children_before_waiting_for_terminal_state`, update expectations:

```python
assert response.child_run_ids == [
    "run-building",
    "run-road",
    "run-water-polygon",
    "run-waterways",
    "run-poi",
]
assert fake.created_task_kinds == [
    "building",
    "road",
    "water_polygon",
    "waterways",
    "poi",
]
assert [item["task_kind"] for item in summary["child_runs"]] == fake.created_task_kinds
assert [item["task_family"] for item in summary["child_runs"]] == [
    "building",
    "road",
    "water",
    "water",
    "poi",
]
```

In `test_scenario_run_service_uses_one_global_child_wait_deadline`, update expected child run ids and queued phases from 3 items to 5 items:

```python
assert response.child_run_ids == [
    "run-building",
    "run-road",
    "run-water-polygon",
    "run-waterways",
    "run-poi",
]
assert response.phase == ScenarioPhase.running
assert [item["phase"] for item in summary["child_runs"]] == [RunPhase.queued.value] * 5
```

- [ ] **Step 2: Run the scenario tests and confirm they fail**

Run:

```powershell
pytest tests/test_scenario_run_service.py -q
```

Expected: FAIL because `ScenarioChildRunSpec` lacks task kind fields and scenario service still builds only 3 flood children.

- [ ] **Step 3: Add task fields to child spec**

Modify `schemas/scenario.py`:

```python
from schemas.task_kind import TaskKind
```

Update `ScenarioChildRunSpec`:

```python
class ScenarioChildRunSpec(BaseModel):
    job_type: JobType
    trigger_content: str
    disaster_type: Optional[str] = None
    spatial_extent: Optional[str] = None
    force_aoi_resolution: bool = False
    target_crs: Optional[str] = None
    debug: bool = False
    task_kind: Optional[TaskKind] = None
    task_family: Optional[str] = None
    preferred_pattern_id: Optional[str] = None
    output_data_type: Optional[str] = None
```

- [ ] **Step 4: Replace child spec expansion with Mission Compiler output**

Modify `services/scenario_run_service.py`.

Add imports:

```python
from schemas.task_kind import TaskKind, task_kind_family
from services.mission_compiler_service import compile_scenario_mission
```

Replace `build_child_run_specs()` with:

```python
def build_child_run_specs(request: ScenarioRunRequest) -> list[ScenarioChildRunSpec]:
    mission = compile_scenario_mission(request)
    return [
        ScenarioChildRunSpec(
            job_type=task.job_type,
            trigger_content=task.trigger_content,
            disaster_type=task.disaster_type,
            spatial_extent=task.spatial_extent,
            force_aoi_resolution=task.force_aoi_resolution,
            target_crs=task.target_crs,
            debug=task.debug,
            task_kind=task.task_kind,
            task_family=task.task_family,
            preferred_pattern_id=task.preferred_pattern_id,
            output_data_type=task.output_data_type,
        )
        for task in mission.child_tasks
    ]
```

Update `_run_child()` to pass the pattern hint:

```python
request = RunCreateRequest(
    job_type=spec.job_type,
    trigger=RunTrigger(
        type=RunTriggerType.user_query,
        content=spec.trigger_content,
        disaster_type=spec.disaster_type,
        spatial_extent=spec.spatial_extent,
        force_aoi_resolution=spec.force_aoi_resolution,
    ),
    target_crs=spec.target_crs,
    field_mapping={},
    debug=spec.debug,
    input_strategy=RunInputStrategy.task_driven_auto,
    preferred_pattern_id=spec.preferred_pattern_id,
)
```

Change the success return call to pass `spec`:

```python
return self._inspect_child_result(run_id=status.run_id, spec=spec, fallback_status=status)
```

Change the failure file stem and payload:

```python
task_key = (spec.task_kind.value if spec.task_kind else spec.job_type.value)
error_path = output_dir / "child_runs" / f"{task_key}-failed.json"
error_payload = {
    "job_type": spec.job_type.value,
    "task_kind": task_key,
    "task_family": spec.task_family or task_kind_family(spec.task_kind) if spec.task_kind else spec.job_type.value,
    "error": f"{type(exc).__name__}: {exc}",
}
```

Update the returned failure dict:

```python
return {
    "run_id": None,
    "job_type": spec.job_type.value,
    "task_kind": task_key,
    "task_family": error_payload["task_family"],
    "phase": ScenarioPhase.failed.value,
    "error": error_payload["error"],
    "plan": None,
    "audit_events": [],
    "artifact_path": None,
}
```

Change `_inspect_child_result()` signature and body:

```python
def _inspect_child_result(self, *, run_id: str, spec: ScenarioChildRunSpec, fallback_status=None) -> dict[str, Any]:
    get_run = getattr(self.agent_run_service, "get_run", None)
    status = get_run(run_id) if callable(get_run) else fallback_status
    if status is None:
        status = fallback_status
    phase = status.phase.value if status is not None else ScenarioPhase.failed.value
    task_key = spec.task_kind.value if spec.task_kind else spec.job_type.value
    return {
        "run_id": run_id,
        "job_type": spec.job_type.value,
        "task_kind": task_key,
        "task_family": spec.task_family or task_key,
        "phase": phase,
        "status": status,
        "plan": self.agent_run_service.get_plan(run_id),
        "audit_events": self.agent_run_service.get_audit_events(run_id),
        "artifact_path": self.agent_run_service.get_artifact_path(run_id),
        "error": getattr(status, "error", None) if status is not None else None,
    }
```

Change `_refresh_started_child_result()` so it rebuilds a minimal spec from stored result metadata:

```python
def _refresh_started_child_result(self, result: dict[str, Any]) -> dict[str, Any]:
    run_id = result.get("run_id")
    if not run_id:
        return result
    try:
        job_type = JobType(str(result.get("job_type")))
    except ValueError:
        return result
    task_kind_value = result.get("task_kind")
    task_kind = TaskKind(str(task_kind_value)) if task_kind_value else None
    spec = ScenarioChildRunSpec(
        job_type=job_type,
        trigger_content="",
        task_kind=task_kind,
        task_family=str(result.get("task_family") or task_kind_value or job_type.value),
    )
    return self._inspect_child_result(run_id=str(run_id), spec=spec, fallback_status=result.get("status"))
```

Update `_child_summary()`:

```python
def _child_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": result.get("run_id"),
        "job_type": result.get("job_type"),
        "task_kind": result.get("task_kind") or result.get("job_type"),
        "task_family": result.get("task_family") or result.get("job_type"),
        "phase": result.get("phase"),
        "artifact_path": str(result.get("artifact_path")) if result.get("artifact_path") else None,
        "error": result.get("error"),
        "degradation": _child_degradation(result),
    }
```

- [ ] **Step 5: Update fake scenario services for duplicate water job types**

In `tests/test_scenario_run_service.py`, update `_FakeAgentRunService.create_run()` to use a task key:

```python
def _task_key_from_request(request) -> str:
    preferred = str(getattr(request, "preferred_pattern_id", "") or "")
    if preferred == "wp.flood.water_polygon.default":
        return "water-polygon"
    if preferred == "wp.flood.waterways.default":
        return "waterways"
    return request.job_type.value
```

Use it in every fake `create_run()`:

```python
task_key = _task_key_from_request(request)
run_id = f"run-{task_key}"
```

In `_StartAllChildrenBeforeTerminalAgentRunService.__init__`, add:

```python
self.created_task_kinds: list[str] = []
```

In its `create_run()`, append:

```python
self.created_task_kinds.append(task_key.replace("-", "_"))
```

Keep `self.created_job_types.append(request.job_type)` if existing tests still assert it; update the assertion to expect `[JobType.building, JobType.road, JobType.water, JobType.water, JobType.poi]`.

- [ ] **Step 6: Run scenario service tests**

Run:

```powershell
pytest tests/test_scenario_run_service.py tests/test_mission_compiler_service.py tests/test_task_kind.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 3**

Run:

```powershell
git add schemas/scenario.py services/scenario_run_service.py tests/test_scenario_run_service.py
git commit -m "feat: run scenario children by task kind"
```

Expected: commit succeeds with only scenario wiring files staged.

### Task 4: Normalize Trigger Events Into Mission Task Kinds

**Files:**
- Modify: `services/scenario_trigger_service.py`
- Modify: `tests/test_scenario_trigger_service.py`

- [ ] **Step 1: Add failing trigger normalization tests**

Append to `tests/test_scenario_trigger_service.py`:

```python
def test_normalize_trigger_event_without_requested_layers_leaves_scope_to_mission_compiler() -> None:
    event = {
        "event_id": "gdacs-2026-018",
        "event_type": "flood",
        "location": "Karachi, Pakistan",
        "description": "Urban flooding",
    }

    request = normalize_trigger_event(event)

    assert request.disaster_type == "flood"
    assert request.job_types == []
    assert request.metadata["requested_task_kinds"] == []
    assert request.metadata["unsupported_requested_layers"] == []


def test_normalize_trigger_event_records_water_family_as_two_task_kinds() -> None:
    event = {
        "event_id": "gdacs-2026-019",
        "event_type": "flood",
        "location": "Nairobi, Kenya",
        "requested_layers": ["water"],
    }

    request = normalize_trigger_event(event)

    assert request.job_types == [JobType.water]
    assert request.metadata["requested_task_kinds"] == ["water_polygon", "waterways"]


def test_normalize_trigger_event_can_request_waterways_only() -> None:
    event = {
        "event_id": "gdacs-2026-020",
        "event_type": "flood",
        "location": "Sindh, Pakistan",
        "requested_layers": ["waterways"],
    }

    request = normalize_trigger_event(event)

    assert request.job_types == [JobType.water]
    assert request.metadata["requested_task_kinds"] == ["waterways"]
```

Update `test_normalize_trigger_event_defaults_layers_and_hashes_missing_event_id` so it no longer expects building plus road for an unsupported-only layer list:

```python
assert request_a.job_types == []
assert request_a.metadata["requested_task_kinds"] == []
assert request_a.metadata["unsupported_requested_layers"] == ["unknown"]
```

- [ ] **Step 2: Run trigger tests and confirm they fail**

Run:

```powershell
pytest tests/test_scenario_trigger_service.py -q
```

Expected: FAIL because trigger service still defaults to building plus road and does not write `requested_task_kinds`.

- [ ] **Step 3: Update trigger normalization**

Modify imports in `services/scenario_trigger_service.py`:

```python
from schemas.task_kind import task_kind_to_job_type
from services.mission_compiler_service import partition_requested_task_kinds
```

Replace the start of `normalize_trigger_event()`:

```python
event_type = _clean_text(event.get("event_type"))
location = _clean_text(event.get("location"))
description = _clean_text(event.get("description"))
task_kinds, unsupported_layers = partition_requested_task_kinds(event.get("requested_layers"))
job_types = _job_types_from_task_kinds(task_kinds)
idempotency_key = _idempotency_key(event)
layer_text = " and ".join(task_kind.value for task_kind in task_kinds) or "bounded geospatial"
```

Update metadata:

```python
"requested_task_kinds": [task_kind.value for task_kind in task_kinds],
"unsupported_requested_layers": unsupported_layers,
```

Replace `_partition_requested_job_types()` with:

```python
def _job_types_from_task_kinds(task_kinds) -> List[JobType]:
    job_types: List[JobType] = []
    for task_kind in task_kinds:
        job_type = task_kind_to_job_type(task_kind)
        if job_type not in job_types:
            job_types.append(job_type)
    return job_types
```

- [ ] **Step 4: Run trigger tests**

Run:

```powershell
pytest tests/test_scenario_trigger_service.py tests/test_mission_compiler_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 4**

Run:

```powershell
git add services/scenario_trigger_service.py tests/test_scenario_trigger_service.py
git commit -m "feat: normalize trigger layers into task kinds"
```

Expected: commit succeeds with only trigger normalization files staged.

### Task 5: Add Mission Metadata To Scenario Summary

**Files:**
- Modify: `services/scenario_run_service.py`
- Modify: `tests/test_scenario_run_service.py`

- [ ] **Step 1: Add failing summary assertions**

In `test_scenario_run_service_starts_all_children_before_waiting_for_terminal_state`, add:

```python
assert summary["mission"]["scope_source"] == "default_disaster_bundle"
assert summary["mission"]["task_kinds"] == [
    "building",
    "road",
    "water_polygon",
    "waterways",
    "poi",
]
assert summary["mission"]["task_families"] == ["building", "road", "water", "poi"]
```

- [ ] **Step 2: Run scenario tests and confirm they fail**

Run:

```powershell
pytest tests/test_scenario_run_service.py::test_scenario_run_service_starts_all_children_before_waiting_for_terminal_state -q
```

Expected: FAIL because summary has no `mission` key.

- [ ] **Step 3: Add mission summary generation**

In `services/scenario_run_service.py`, update `_build_summary()`:

```python
mission = compile_scenario_mission(request)
```

Add this key to the returned summary dict:

```python
"mission": {
    "scope_source": mission.scope_source,
    "task_kinds": [task.task_kind.value for task in mission.child_tasks],
    "task_families": mission.task_families,
    "unsupported_layers": mission.unsupported_layers,
},
```

Keep `child_runs` as child-level execution evidence; `mission` is the expected scope evidence.

- [ ] **Step 4: Run summary tests**

Run:

```powershell
pytest tests/test_scenario_run_service.py tests/test_scenario_report_service.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

Run:

```powershell
git add services/scenario_run_service.py tests/test_scenario_run_service.py
git commit -m "feat: record mission task scope in scenario summaries"
```

Expected: commit succeeds with only summary evidence files staged.

### Task 6: Final Verification

**Files:**
- No new implementation files.
- Verification covers the first-batch integration surface.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
pytest tests/test_task_kind.py tests/test_mission_compiler_service.py tests/test_scenario_trigger_service.py tests/test_scenario_run_service.py tests/test_tool_registry.py tests/test_planner_context.py tests/test_kg_repository_enhancements.py::test_inmemory_repository_returns_water_pattern_and_task_driven_bundle_sources -q
```

Expected: PASS.

- [ ] **Step 2: Run existing large-area water and POI runtime tests**

Run:

```powershell
pytest tests/test_agent_run_service_large_area_runtime.py tests/test_large_area_runtime_service.py tests/test_waterways_conflation_v7.py -q
```

Expected: PASS. These tests prove the first-batch scenario split still lands on existing water polygon and waterways runtime material.

- [ ] **Step 3: Check anti-patterns**

Run:

```powershell
rg -n "waterways\\s*=|water_polygon\\s*=" schemas/fusion.py
```

Expected: no output. `JobType` must not be extended in this slice.

Run:

```powershell
rg -n "recovering|ScenarioPhase\\.recovering" schemas services tests
```

Expected: no output. Scenario status vocabulary must remain `queued`, `running`, `succeeded`, `partial`, `failed`.

- [ ] **Step 4: Inspect final git diff**

Run:

```powershell
git status --short
git diff --stat
```

Expected: only files from this plan are modified or newly created. Existing unrelated dirty files remain untouched.

- [ ] **Step 5: Commit final verification note if needed**

If no code changed during verification, do not create an empty commit. If tests required a small fix, commit only the files touched by that fix:

```powershell
git add schemas/task_kind.py schemas/mission.py services/mission_compiler_service.py schemas/scenario.py services/scenario_run_service.py services/scenario_trigger_service.py tests/test_task_kind.py tests/test_mission_compiler_service.py tests/test_scenario_run_service.py tests/test_scenario_trigger_service.py
git commit -m "test: verify mission compiler task split"
```

## Self-Review

- Spec coverage:
  - Full disaster bundle is covered by Task 2 and Task 3.
  - Public four-family surface with five executable child tasks is covered by Task 1 and Task 5.
  - `water_polygon` and `waterways` independent reporting is covered by Task 3 and Task 5.
  - Compatibility with direct single-layer requests is covered by Task 2.
  - Existing `partial` semantics are preserved because this plan does not change `_phase_from_child_results()` or scenario status values.
- Placeholders:
  - This plan contains only concrete file paths, test commands, and implementation snippets.
- Type consistency:
  - `TaskKind.water_polygon` and `TaskKind.waterways` both map to `JobType.water`.
  - `ScenarioChildRunSpec.preferred_pattern_id` maps into existing `RunCreateRequest.preferred_pattern_id`.
  - `mission.task_kinds` stores task-kind strings; child summaries store both `job_type` and `task_kind`.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-03-mission-compiler-task-kind-water-split.md`.

Two execution options:

**1. Subagent-Driven (recommended)** - Dispatch a fresh worker per task, review between tasks, and keep each commit small.

**2. Inline Execution** - Execute tasks in this session with checkpoints after each task.
