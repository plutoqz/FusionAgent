from __future__ import annotations

import os
from typing import Any, Iterable

from kg.knowledge_release import KnowledgeReleaseError
from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry
from schemas.fusion import JobType
from schemas.mission import MissionSpec, MissionTaskSpec
from schemas.scenario import ScenarioRunRequest
from schemas.task_kind import TaskKind, normalize_task_kind
from services.scenario_trigger_normalizer import normalize_scenario_trigger_text


def partition_requested_task_kinds(
    raw_layers: Any,
    *,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> tuple[list[TaskKind], list[str]]:
    registry = policy_registry or default_policy_registry()
    task_kinds: list[TaskKind] = []
    unsupported_layers: list[str] = []
    layers = raw_layers if isinstance(raw_layers, list) else []
    for layer in layers:
        normalized = (
            [TaskKind(item) for item in registry.task_kinds_for_alias(layer)]
            if policy_registry is not None
            else normalize_task_kind(layer)
        )
        if not normalized:
            layer_text = str(layer).strip().lower()
            if layer_text and layer_text not in unsupported_layers:
                unsupported_layers.append(layer_text)
            continue
        for task_kind in normalized:
            if task_kind not in task_kinds:
                task_kinds.append(task_kind)
    return task_kinds, unsupported_layers


def compile_scenario_mission(
    request: ScenarioRunRequest,
    *,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> MissionSpec:
    registry = policy_registry or default_policy_registry()
    request = _request_with_normalized_trigger(request, registry)
    task_kinds, scope_source, unsupported_requested_layers, task_bundle_id = _resolve_task_kinds(
        request,
        registry,
    )
    if _p3_variant() == "fixed_priority":
        task_kinds = sorted(
            task_kinds,
            key=lambda task_kind: int(registry.task_record(task_kind.value).get("execution_order", 0)),
        )
    child_tasks = [_build_task_spec(request, task_kind, registry) for task_kind in task_kinds]
    task_families = _dedupe(task.task_family for task in child_tasks)
    unsupported = _dedupe(
        [
            *unsupported_requested_layers,
            *[
                str(item).strip().lower()
                for item in (request.metadata.get("unsupported_requested_layers") or [])
                if str(item).strip()
            ],
        ]
    )
    return MissionSpec(
        scope_source=scope_source,
        task_bundle_id=task_bundle_id,
        child_tasks=child_tasks,
        task_families=task_families,
        unsupported_layers=unsupported,
        knowledge_identity=registry.knowledge_identity(),
        knowledge_refs=[
            *([f"disaster_vocabulary:{request.disaster_type}"] if request.disaster_type else []),
            *([f"task_bundle:{task_bundle_id}"] if task_bundle_id else []),
            *[f"task_semantics:{task_kind.value}" for task_kind in task_kinds],
        ],
    )


def _request_with_normalized_trigger(
    request: ScenarioRunRequest,
    registry: KnowledgePolicyRegistry,
) -> ScenarioRunRequest:
    normalized = normalize_scenario_trigger_text(request.trigger_content, policy_registry=registry)
    updates: dict[str, Any] = {}
    metadata = dict(request.metadata or {})
    if normalized.confidence > 0:
        metadata.setdefault("normalized_trigger", normalized.to_dict())
        updates["metadata"] = metadata
    disaster_type = _normalize_disaster_type(request.disaster_type or normalized.disaster_type, registry)
    if disaster_type and disaster_type != request.disaster_type:
        updates["disaster_type"] = disaster_type
    if not str(request.spatial_extent or "").strip() and normalized.normalized_location:
        updates["spatial_extent"] = normalized.normalized_location
    return request.model_copy(update=updates) if updates else request


def _resolve_task_kinds(
    request: ScenarioRunRequest,
    registry: KnowledgePolicyRegistry,
) -> tuple[list[TaskKind], str, list[str], str | None]:
    mission_policy = registry.mission_policy()
    requested_task_kinds = request.metadata.get("requested_task_kinds")
    if isinstance(requested_task_kinds, list) and (
        requested_task_kinds or request.metadata.get("requested_layers_present") is True
    ):
        task_kinds, unsupported_layers = partition_requested_task_kinds(
            requested_task_kinds,
            policy_registry=registry,
        )
        return task_kinds, str(mission_policy["explicit_task_scope_source"]), unsupported_layers, None

    if request.job_types:
        task_kinds = []
        for job_type in request.job_types:
            for item in registry.task_kinds_for_job_type(job_type.value):
                task_kind = TaskKind(item)
                if task_kind not in task_kinds:
                    task_kinds.append(task_kind)
        return task_kinds, str(mission_policy["explicit_job_scope_source"]), [], None

    if _is_disaster_scenario(request, registry):
        disaster_type = _normalize_disaster_type(request.disaster_type, registry)
        if not disaster_type:
            disaster_type = registry.disaster_type_in_text(
                " ".join([request.scenario_name, request.trigger_content])
            )
        if not disaster_type:
            raise KnowledgeReleaseError("Disaster scenario could not be grounded to KG disaster vocabulary")
        disaster_record = registry.disaster_record(disaster_type)
        task_bundle_id = str(disaster_record.get("default_task_bundle_id") or "").strip()
        if not task_bundle_id:
            raise KnowledgeReleaseError(
                f"KG disaster record {disaster_type} has no default_task_bundle_id"
            )
        task_kinds = _task_kinds_for_bundle(task_bundle_id, registry)
        return task_kinds, str(mission_policy["disaster_scope_source"]), [], task_bundle_id

    detected = _task_kinds_from_text(" ".join([request.scenario_name, request.trigger_content]), registry)
    if detected:
        return detected, str(mission_policy["detected_task_scope_source"]), [], None

    default_task_kind = TaskKind(str(mission_policy["default_direct_task_kind"]))
    return [default_task_kind], str(mission_policy["default_task_scope_source"]), [], None


def _task_kinds_for_bundle(
    task_bundle_id: str,
    registry: KnowledgePolicyRegistry,
) -> list[TaskKind]:
    bundle = registry.task_bundle_record(task_bundle_id)
    requested_task_ids = bundle.get("requested_tasks")
    if not isinstance(requested_task_ids, list) or not requested_task_ids:
        raise KnowledgeReleaseError(f"KG TaskBundle {task_bundle_id} has no requested_tasks")

    task_kinds: list[TaskKind] = []
    seen_task_ids: set[str] = set()
    for raw_task_id in requested_task_ids:
        task_id = str(raw_task_id or "").strip()
        if not task_id:
            raise KnowledgeReleaseError(f"KG TaskBundle {task_bundle_id} contains an empty task ID")
        if task_id in seen_task_ids:
            raise KnowledgeReleaseError(
                f"KG TaskBundle {task_bundle_id} contains duplicate task ID {task_id}"
            )
        seen_task_ids.add(task_id)
        task_record = registry.task_record_by_id(task_id)
        try:
            task_kinds.append(TaskKind(str(task_record["task_kind"])))
        except (KeyError, ValueError) as exc:
            raise KnowledgeReleaseError(
                f"KG task {task_id} in TaskBundle {task_bundle_id} has no executable task_kind"
            ) from exc
    return task_kinds


def _is_disaster_scenario(request: ScenarioRunRequest, registry: KnowledgePolicyRegistry) -> bool:
    if str(request.disaster_type or "").strip():
        return registry.resolve_disaster_type(request.disaster_type) is not None
    text = " ".join([request.scenario_name, request.trigger_content]).casefold()
    return registry.disaster_type_in_text(text) is not None


def _normalize_disaster_type(
    value: str | None,
    registry: KnowledgePolicyRegistry,
) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = registry.resolve_disaster_type(text)
    if normalized is None:
        raise KnowledgeReleaseError(f"Unknown disaster type in frozen KG vocabulary: {text}")
    return normalized


def _task_kinds_from_text(text: str, registry: KnowledgePolicyRegistry) -> list[TaskKind]:
    return [TaskKind(item) for item in registry.task_kinds_in_text(text)]


def _build_task_spec(
    request: ScenarioRunRequest,
    task_kind: TaskKind,
    registry: KnowledgePolicyRegistry,
) -> MissionTaskSpec:
    task_record = registry.task_record(task_kind.value)
    return MissionTaskSpec(
        task_kind=task_kind,
        task_family=str(task_record["family"]),
        job_type=JobType(str(task_record["job_type"])),
        trigger_content=_task_trigger_content(request.trigger_content, task_kind, registry),
        disaster_type=request.disaster_type,
        spatial_extent=request.spatial_extent,
        force_aoi_resolution=request.force_aoi_resolution,
        target_crs=request.target_crs,
        debug=request.debug,
        preferred_pattern_id=(
            str(task_record["preferred_pattern_id"])
            if task_record.get("preferred_pattern_id")
            else None
        ),
        output_data_type=str(task_record["output_data_type"]),
    )


def _task_trigger_content(
    base: str,
    task_kind: TaskKind,
    registry: KnowledgePolicyRegistry,
) -> str:
    clean = str(base or "").strip()
    suffix = registry.task_record(task_kind.value).get("instruction_suffix")
    return f"{clean}; {suffix}" if suffix else clean


def _dedupe(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def _p3_variant() -> str:
    return os.getenv("GEOFUSION_P3_VARIANT", "full_method").strip().lower()
