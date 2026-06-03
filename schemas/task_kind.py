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
