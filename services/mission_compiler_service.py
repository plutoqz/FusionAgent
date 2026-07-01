from __future__ import annotations

import re
from typing import Any, Iterable

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
from services.scenario_trigger_normalizer import normalize_scenario_trigger_text

_ENGLISH_DISASTER_KEYWORDS = (
    "flood",
    "heavy rainfall",
    "heavy_rainfall",
    "rainstorm",
    "earthquake",
    "typhoon",
    "disaster",
    "emergency",
)

_CHINESE_DISASTER_KEYWORDS = (
    "洪涝",
    "洪水",
    "内涝",
    "强降雨",
    "暴雨",
    "降雨",
    "地震",
    "台风",
    "灾害",
    "应急",
)

_FLOOD_ALIASES = {"flood", "heavy_rainfall", "heavy rainfall", "rainstorm", "洪涝", "洪水", "内涝", "强降雨", "暴雨"}


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
    request = _request_with_normalized_trigger(request)
    task_kinds, scope_source, unsupported_requested_layers = _resolve_task_kinds(request)
    child_tasks = [_build_task_spec(request, task_kind) for task_kind in task_kinds]
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
        child_tasks=child_tasks,
        task_families=task_families,
        unsupported_layers=unsupported,
    )


def _request_with_normalized_trigger(request: ScenarioRunRequest) -> ScenarioRunRequest:
    normalized = normalize_scenario_trigger_text(request.trigger_content)
    updates: dict[str, Any] = {}
    metadata = dict(request.metadata or {})
    if normalized.confidence > 0:
        metadata.setdefault("normalized_trigger", normalized.to_dict())
        updates["metadata"] = metadata
    disaster_type = _normalize_disaster_type(request.disaster_type or normalized.disaster_type)
    if disaster_type and disaster_type != request.disaster_type:
        updates["disaster_type"] = disaster_type
    if not str(request.spatial_extent or "").strip() and normalized.normalized_location:
        updates["spatial_extent"] = normalized.normalized_location
    return request.model_copy(update=updates) if updates else request


def _resolve_task_kinds(request: ScenarioRunRequest) -> tuple[list[TaskKind], str, list[str]]:
    requested_task_kinds = request.metadata.get("requested_task_kinds")
    if isinstance(requested_task_kinds, list) and (
        requested_task_kinds or request.metadata.get("requested_layers_present") is True
    ):
        task_kinds, unsupported_layers = partition_requested_task_kinds(requested_task_kinds)
        return task_kinds, "explicit_task_kinds", unsupported_layers

    if request.job_types:
        task_kinds = []
        for job_type in request.job_types:
            for task_kind in expand_job_type_to_task_kinds(job_type):
                if task_kind not in task_kinds:
                    task_kinds.append(task_kind)
        return task_kinds, "explicit_job_types", []

    if _is_disaster_scenario(request):
        return list(FULL_DISASTER_TASK_KINDS), "default_disaster_bundle", []

    detected = _task_kinds_from_text(" ".join([request.scenario_name, request.trigger_content]))
    if detected:
        return detected, "detected_direct_task", []

    return [TaskKind.building], "default_building", []


def _is_disaster_scenario(request: ScenarioRunRequest) -> bool:
    if str(request.disaster_type or "").strip():
        return True
    text = " ".join([request.scenario_name, request.trigger_content]).casefold()
    if any(keyword in text for keyword in _CHINESE_DISASTER_KEYWORDS):
        return True
    return any(_contains_english_token(text, keyword) for keyword in _ENGLISH_DISASTER_KEYWORDS)


def _normalize_disaster_type(value: str | None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.casefold().replace("-", "_")
    if normalized in _FLOOD_ALIASES or text in _FLOOD_ALIASES:
        return "flood"
    return normalized


def _task_kinds_from_text(text: str) -> list[TaskKind]:
    found: list[TaskKind] = []
    lowered = text.casefold()
    for token in ("building", "road", "water", "waterways", "river", "poi"):
        if not _contains_english_token(lowered, token):
            continue
        for task_kind in normalize_task_kind(token):
            if task_kind not in found:
                found.append(task_kind)
    return found


def _contains_english_token(text: str, token: str) -> bool:
    pattern = rf"(?<![0-9a-z_]){re.escape(token.casefold())}(?![0-9a-z_])"
    return re.search(pattern, text) is not None


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
