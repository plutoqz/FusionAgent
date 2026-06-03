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


def test_requested_task_kind_metadata_records_mixed_invalid_layers() -> None:
    request = ScenarioRunRequest(
        scenario_name="Pakistan waterways",
        trigger_content="fuse river data for Pakistan",
        metadata={
            "requested_task_kinds": ["waterways", "traffic", "waterways"],
            "unsupported_requested_layers": ["parcel", "traffic", "parcel"],
        },
    )

    mission = compile_scenario_mission(request)

    assert [task.task_kind for task in mission.child_tasks] == [TaskKind.waterways]
    assert mission.scope_source == "explicit_task_kinds"
    assert mission.unsupported_layers == ["traffic", "parcel"]


def test_all_invalid_requested_task_kinds_do_not_fall_back_to_defaults() -> None:
    request = ScenarioRunRequest(
        scenario_name="Karachi flood",
        trigger_content="Karachi has flood impacts near a road.",
        disaster_type="flood",
        metadata={"requested_task_kinds": ["traffic", "parcel", "traffic"]},
    )

    mission = compile_scenario_mission(request)

    assert mission.child_tasks == []
    assert mission.task_families == []
    assert mission.scope_source == "explicit_task_kinds"
    assert mission.unsupported_layers == ["traffic", "parcel"]


def test_explicit_job_types_take_priority_over_disaster_defaults() -> None:
    request = ScenarioRunRequest(
        scenario_name="Karachi flood buildings",
        trigger_content="Karachi has a flood disaster, but only buildings are requested.",
        disaster_type="flood",
        job_types=[JobType.building],
    )

    mission = compile_scenario_mission(request)

    assert [task.task_kind for task in mission.child_tasks] == [TaskKind.building]
    assert mission.scope_source == "explicit_job_types"


def test_english_keyword_detection_ignores_substring_false_positives() -> None:
    request = ScenarioRunRequest(
        scenario_name="Product roadmap",
        trigger_content="The waterfall chart uses a floodlight label.",
    )

    mission = compile_scenario_mission(request)

    assert [task.task_kind for task in mission.child_tasks] == [TaskKind.building]
    assert mission.scope_source == "default_building"


def test_partition_requested_task_kinds_deduplicates_and_records_unsupported_layers() -> None:
    task_kinds, unsupported = partition_requested_task_kinds(["water", "river", "traffic"])

    assert task_kinds == [TaskKind.water_polygon, TaskKind.waterways]
    assert unsupported == ["traffic"]
