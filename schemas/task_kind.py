from __future__ import annotations

from enum import Enum

from kg.knowledge_release import KnowledgeReleaseError
from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry
from schemas.fusion import JobType


class TaskKind(str, Enum):
    building = "building"
    road = "road"
    water_polygon = "water_polygon"
    waterways = "waterways"
    poi = "poi"


def _registry() -> KnowledgePolicyRegistry:
    return default_policy_registry()


def _task_record(task_kind: TaskKind) -> dict[str, object]:
    return _registry().task_record(task_kind.value)


def _default_disaster_task_kinds() -> tuple[TaskKind, ...]:
    registry = _registry()
    generic_disaster = registry.disaster_record("generic")
    bundle_id = str(generic_disaster.get("default_task_bundle_id") or "").strip()
    bundle = registry.task_bundle_record(bundle_id)
    requested_tasks = bundle.get("requested_tasks")
    if not isinstance(requested_tasks, list) or not requested_tasks:
        raise KnowledgeReleaseError(f"Frozen TaskBundle {bundle_id!r} has no requested_tasks")
    return tuple(
        TaskKind(str(registry.task_record_by_id(str(task_id))["task_kind"]))
        for task_id in requested_tasks
    )


FULL_DISASTER_TASK_KINDS: tuple[TaskKind, ...] = _default_disaster_task_kinds()


def task_kind_to_job_type(task_kind: TaskKind) -> JobType:
    return JobType(str(_task_record(task_kind)["job_type"]))


def task_kind_family(task_kind: TaskKind) -> str:
    return str(_task_record(task_kind)["family"])


def task_kind_output_type(task_kind: TaskKind) -> str:
    return str(_task_record(task_kind)["output_data_type"])


def task_kind_preferred_pattern_id(task_kind: TaskKind, disaster_type: str | None) -> str | None:
    value = _task_record(task_kind).get("preferred_pattern_id")
    return str(value) if value else None


def expand_job_type_to_task_kinds(job_type: JobType) -> list[TaskKind]:
    return [TaskKind(value) for value in _registry().task_kinds_for_job_type(job_type.value)]


def normalize_task_kind(value: object) -> list[TaskKind]:
    return [TaskKind(item) for item in _registry().task_kinds_for_alias(value)]
