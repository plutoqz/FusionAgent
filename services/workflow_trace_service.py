from __future__ import annotations

from typing import Any

from schemas.agent import RunEvent


EVENT_TO_STEP = {
    "run_started": "run_started",
    "aoi_resolved": "aoi_resolved",
    "target_crs_resolved": "target_crs_resolved",
    "plan_created": "kg_path_selected",
    "plan_validated": "plan_validated",
    "post_acquisition_planning_started": "post_acquisition_planning_started",
    "post_acquisition_plan_created": "post_acquisition_plan_created",
    "data_requirements_resolved": "data_requirements_resolved",
    "source_acquisition_started": "source_acquisition_started",
    "source_acquisition_heartbeat": "source_acquisition_heartbeat",
    "source_acquisition_failed": "source_acquisition_failed",
    "source_materialized": "source_materialized",
    "source_coverage_checked": "source_coverage_checked",
    "source_fallback_selected": "source_fallback_selected",
    "source_clipped": "source_clipped",
    "input_bundle_created": "input_bundle_created",
    "task_inputs_resolved": "task_inputs_resolved",
    "step_started": "step_started",
    "step_succeeded": "step_succeeded",
    "step_failed": "step_failed",
    "execution_completed": "fusion_executed",
    "execution_started": "execution_started",
    "quality_gate_evaluated": "quality_gate_evaluated",
    "quality_gate_disabled_for_ablation": "quality_gate_disabled_for_ablation",
    "artifact_repair_started": "artifact_repair_started",
    "artifact_repair_applied": "artifact_repair_applied",
    "artifact_repair_exhausted": "artifact_repair_exhausted",
    "replan_requested": "replan_requested",
    "replan_applied": "replan_applied",
    "replan_rejected": "replan_rejected",
    "run_succeeded": "artifact_written",
    "run_failed": "failure_recorded",
}

STEP_EVENT_STATUS = {
    "run_started": "started",
    "post_acquisition_planning_started": "started",
    "source_acquisition_started": "started",
    "source_acquisition_heartbeat": "running",
    "source_acquisition_failed": "failed",
    "execution_started": "started",
    "artifact_repair_started": "started",
    "artifact_repair_exhausted": "exhausted",
    "replan_requested": "requested",
    "replan_rejected": "rejected",
    "quality_gate_disabled_for_ablation": "disabled",
    "step_started": "started",
    "step_succeeded": "succeeded",
    "step_failed": "failed",
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
                "status": _status_for_event(event),
                "phase": event.phase.value,
                "timestamp": event.timestamp,
                "event_kind": event.kind,
                "plan_revision": event.plan_revision,
                "attempt_no": event.attempt_no,
                "input": _event_input(event),
                "output": _event_output(event),
                "details": event.details,
            }
        )
    return {"steps": steps}


def _actor_for_event(kind: str) -> str:
    if kind.startswith(("source_", "quality_gate_", "artifact_repair_")) or kind == "input_bundle_created":
        return "runtime"
    return "agent"


def _status_for_event(event: RunEvent) -> str:
    kind = event.kind
    # An evaluation can complete successfully while rejecting the artifact.
    if kind == "quality_gate_evaluated":
        accepted = (event.details or {}).get("accepted")
        if accepted is True:
            return "accepted"
        if accepted is False:
            return "rejected"
        return "unknown"
    if kind in STEP_EVENT_STATUS:
        return STEP_EVENT_STATUS[kind]
    return "failed" if kind == "run_failed" else "succeeded"


def _event_input(event: RunEvent) -> dict[str, Any]:
    details = event.details or {}
    keys = {
        "aoi_resolved": ["query"],
        "target_crs_resolved": ["source"],
        "plan_created": ["workflow_id", "planning_mode", "planning_source"],
        "task_inputs_resolved": ["source_id", "requested_source_id"],
        "step_started": ["step", "algorithm_id", "data_source_id"],
        "step_succeeded": ["step", "algorithm_id", "data_source_id"],
        "step_failed": ["step", "algorithm_id", "data_source_id"],
        "execution_completed": ["repair_count"],
    }.get(event.kind, [])
    return {key: details.get(key) for key in keys if key in details}


def _event_output(event: RunEvent) -> dict[str, Any]:
    details = event.details or {}
    if event.kind == "step_failed":
        error = details.get("error") or event.message
        return {"error": error} if error else {}
    keys = {
        "aoi_resolved": ["display_name", "bbox"],
        "target_crs_resolved": ["target_crs"],
        "plan_created": ["selected_pattern", "selected_decisions"],
        "task_inputs_resolved": ["selected_source_id", "osm_zip_name", "ref_zip_name"],
        "step_succeeded": ["effective_algorithm_id"],
        "execution_completed": ["repair_count"],
        "run_succeeded": ["artifact"],
        "run_failed": ["error"],
    }.get(event.kind, [])
    return {key: details.get(key) for key in keys if key in details}
