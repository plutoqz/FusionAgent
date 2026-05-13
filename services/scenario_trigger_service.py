from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List

from schemas.fusion import JobType
from schemas.scenario import ScenarioRunRequest


def normalize_trigger_event(event: dict[str, Any]) -> ScenarioRunRequest:
    event_type = _clean_text(event.get("event_type"))
    location = _clean_text(event.get("location"))
    description = _clean_text(event.get("description"))
    job_types, unsupported_layers = _partition_requested_job_types(event.get("requested_layers"))
    idempotency_key = _idempotency_key(event)
    layer_text = " and ".join(job_type.value for job_type in job_types)
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


def _partition_requested_job_types(raw_layers: Any) -> tuple[List[JobType], List[str]]:
    job_types: List[JobType] = []
    unsupported_layers: List[str] = []
    layers = raw_layers if isinstance(raw_layers, list) else []
    for layer in layers:
        layer_text = str(layer).strip().lower()
        try:
            job_type = JobType(layer_text)
        except ValueError:
            if layer_text and layer_text not in unsupported_layers:
                unsupported_layers.append(layer_text)
            continue
        if job_type not in job_types:
            job_types.append(job_type)
    return (job_types or [JobType.building, JobType.road], unsupported_layers)


def _idempotency_key(event: Dict[str, Any]) -> str:
    event_id = _clean_text(event.get("event_id"))
    if event_id:
        return event_id
    stable_payload = json.dumps(event, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(stable_payload.encode("utf-8")).hexdigest()
