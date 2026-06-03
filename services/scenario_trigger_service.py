from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from schemas.fusion import JobType
from schemas.scenario import ScenarioRunRequest
from schemas.task_kind import task_kind_to_job_type
from services.mission_compiler_service import partition_requested_task_kinds


def normalize_trigger_event(event: dict[str, Any]) -> ScenarioRunRequest:
    event_type = _clean_text(event.get("event_type"))
    location = _clean_text(event.get("location"))
    description = _clean_text(event.get("description"))
    task_kinds, unsupported_layers = partition_requested_task_kinds(event.get("requested_layers"))
    job_types = _job_types_from_task_kinds(task_kinds)
    idempotency_key = _idempotency_key(event)
    layer_text = " and ".join(task_kind.value for task_kind in task_kinds) or "bounded geospatial"
    trigger_content = f"fuse {layer_text} data for {location or 'the affected area'}"
    if event_type:
        trigger_content = f"{trigger_content} after a {event_type}"
    if description:
        trigger_content = f"{trigger_content}: {description}"

    return ScenarioRunRequest(
        scenario_name=_scenario_name(event_type=event_type, location=location),
        trigger_content=trigger_content,
        disaster_type=event_type or None,
        job_types=job_types,
        metadata={
            "idempotency_key": idempotency_key,
            "event_id": event.get("event_id"),
            "trigger_event": dict(event),
            "requested_task_kinds": [task_kind.value for task_kind in task_kinds],
            "unsupported_requested_layers": unsupported_layers,
        },
    )


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _scenario_name(*, event_type: str, location: str) -> str:
    if event_type and location:
        return f"{location} {event_type}"
    if location:
        return f"{location} scenario"
    if event_type:
        return f"{event_type} scenario"
    return "triggered scenario"


def _job_types_from_task_kinds(task_kinds) -> List[JobType]:
    job_types: List[JobType] = []
    for task_kind in task_kinds:
        job_type = task_kind_to_job_type(task_kind)
        if job_type not in job_types:
            job_types.append(job_type)
    return job_types


def _idempotency_key(event: Dict[str, Any]) -> str:
    event_id = _clean_text(event.get("event_id"))
    if event_id:
        return event_id
    stable_payload = json.dumps(event, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(stable_payload.encode("utf-8")).hexdigest()
