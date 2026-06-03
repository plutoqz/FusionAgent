from __future__ import annotations

from schemas.fusion import JobType
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


def test_full_disaster_task_kinds_records_internal_execution_order() -> None:
    assert FULL_DISASTER_TASK_KINDS == (
        TaskKind.building,
        TaskKind.road,
        TaskKind.water_polygon,
        TaskKind.waterways,
        TaskKind.poi,
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


def test_non_water_job_types_expand_to_matching_single_task_kind() -> None:
    assert expand_job_type_to_task_kinds(JobType.building) == [TaskKind.building]
    assert expand_job_type_to_task_kinds(JobType.road) == [TaskKind.road]
    assert expand_job_type_to_task_kinds(JobType.poi) == [TaskKind.poi]


def test_task_kind_pattern_hints_are_only_needed_for_water_split() -> None:
    assert task_kind_preferred_pattern_id(TaskKind.water_polygon, "flood") == "wp.flood.water_polygon.default"
    assert task_kind_preferred_pattern_id(TaskKind.waterways, "flood") == "wp.flood.waterways.default"
    assert task_kind_preferred_pattern_id(TaskKind.building, "flood") is None
    assert task_kind_preferred_pattern_id(TaskKind.road, "flood") is None
    assert task_kind_preferred_pattern_id(TaskKind.poi, "flood") is None


def test_water_pattern_hints_preserve_current_compatibility_bridge() -> None:
    expected_hints = {
        TaskKind.water_polygon: "wp.flood.water_polygon.default",
        TaskKind.waterways: "wp.flood.waterways.default",
    }

    for disaster_type in (None, "flood", "earthquake"):
        assert task_kind_preferred_pattern_id(TaskKind.water_polygon, disaster_type) == expected_hints[TaskKind.water_polygon]
        assert task_kind_preferred_pattern_id(TaskKind.waterways, disaster_type) == expected_hints[TaskKind.waterways]


def test_normalize_task_kind_accepts_aliases() -> None:
    assert normalize_task_kind("water") == [TaskKind.water_polygon, TaskKind.waterways]
    assert normalize_task_kind("water_polygon") == [TaskKind.water_polygon]
    assert normalize_task_kind("water-polygons") == [TaskKind.water_polygon]
    assert normalize_task_kind("waterways") == [TaskKind.waterways]
    assert normalize_task_kind("river") == [TaskKind.waterways]
    assert normalize_task_kind("poi") == [TaskKind.poi]
    assert normalize_task_kind("point of interest") == [TaskKind.poi]
