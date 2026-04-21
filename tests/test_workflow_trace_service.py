from schemas.agent import RunEvent, RunPhase
from services.workflow_trace_service import build_workflow_trace


def test_build_workflow_trace_normalizes_runtime_events() -> None:
    trace = build_workflow_trace(_make_audit_events_for_successful_road_run())

    step_names = [step["step_name"] for step in trace["steps"]]
    assert step_names == [
        "aoi_resolved",
        "target_crs_resolved",
        "kg_path_selected",
        "plan_validated",
        "task_inputs_resolved",
        "fusion_executed",
        "artifact_written",
    ]
    assert trace["steps"][0]["actor"] == "agent"


def _make_audit_events_for_successful_road_run() -> list[RunEvent]:
    return [
        RunEvent(timestamp="2026-04-21T00:00:00+00:00", kind="aoi_resolved", phase=RunPhase.planning, message="aoi"),
        RunEvent(timestamp="2026-04-21T00:00:01+00:00", kind="target_crs_resolved", phase=RunPhase.planning, message="crs"),
        RunEvent(timestamp="2026-04-21T00:00:02+00:00", kind="plan_created", phase=RunPhase.validating, message="plan"),
        RunEvent(timestamp="2026-04-21T00:00:03+00:00", kind="plan_validated", phase=RunPhase.running, message="valid"),
        RunEvent(timestamp="2026-04-21T00:00:04+00:00", kind="task_inputs_resolved", phase=RunPhase.running, message="inputs"),
        RunEvent(timestamp="2026-04-21T00:00:05+00:00", kind="execution_completed", phase=RunPhase.running, message="exec"),
        RunEvent(timestamp="2026-04-21T00:00:06+00:00", kind="run_succeeded", phase=RunPhase.succeeded, message="ok"),
    ]
