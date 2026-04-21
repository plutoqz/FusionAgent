from __future__ import annotations

from typing import Any

from schemas.agent import RunEvent


EVENT_TO_STEP = {
    "aoi_resolved": "aoi_resolved",
    "target_crs_resolved": "target_crs_resolved",
    "plan_created": "kg_path_selected",
    "plan_validated": "plan_validated",
    "source_coverage_checked": "source_coverage_checked",
    "source_fallback_selected": "source_fallback_selected",
    "source_clipped": "source_clipped",
    "input_bundle_created": "input_bundle_created",
    "task_inputs_resolved": "task_inputs_resolved",
    "execution_completed": "fusion_executed",
    "run_succeeded": "artifact_written",
    "run_failed": "failure_recorded",
}


def build_workflow_trace(events: list[RunEvent]) -> dict[str, Any]:
    steps = []
    for event in events:
        step_name = EVENT_TO_STEP.get(event.kind)
        if step_name is None:
            continue
        steps.append(
            {
                "step_name": step_name,
                "actor": _actor_for_event(event.kind),
                "status": "failed" if event.kind == "run_failed" else "succeeded",
                "phase": event.phase.value,
                "timestamp": event.timestamp,
                "input": _event_input(event),
                "output": _event_output(event),
                "details": event.details,
            }
        )
    return {"steps": steps}


def _actor_for_event(kind: str) -> str:
    if kind in {"source_coverage_checked", "source_fallback_selected", "source_clipped", "input_bundle_created"}:
        return "runtime"
    return "agent"


def _event_input(event: RunEvent) -> dict[str, Any]:
    details = event.details or {}
    keys = {
        "aoi_resolved": ["query"],
        "target_crs_resolved": ["source"],
        "plan_created": ["workflow_id", "planning_mode"],
        "task_inputs_resolved": ["source_id", "requested_source_id"],
        "execution_completed": ["repair_count"],
    }.get(event.kind, [])
    return {key: details.get(key) for key in keys if key in details}


def _event_output(event: RunEvent) -> dict[str, Any]:
    details = event.details or {}
    keys = {
        "aoi_resolved": ["display_name", "bbox"],
        "target_crs_resolved": ["target_crs"],
        "plan_created": ["selected_pattern", "selected_decisions"],
        "task_inputs_resolved": ["selected_source_id", "osm_zip_name", "ref_zip_name"],
        "execution_completed": ["repair_count"],
        "run_succeeded": ["artifact"],
        "run_failed": ["error"],
    }.get(event.kind, [])
    return {key: details.get(key) for key in keys if key in details}
