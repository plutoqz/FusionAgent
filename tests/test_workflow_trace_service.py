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
    assert trace["steps"][2]["input"]["planning_source"] == "llm"


def test_build_workflow_trace_includes_step_lifecycle_events() -> None:
    trace = build_workflow_trace(
        [
            RunEvent(
                timestamp="2026-04-21T00:00:05+00:00",
                kind="step_started",
                phase=RunPhase.running,
                message="step started",
                current_step=1,
                details={
                    "status": "started",
                    "step": 1,
                    "algorithm_id": "algo.fusion.road.conflation.v7",
                    "data_source_id": "catalog.flood.road",
                },
            ),
            RunEvent(
                timestamp="2026-04-21T00:00:06+00:00",
                kind="step_succeeded",
                phase=RunPhase.running,
                message="step succeeded",
                current_step=1,
                details={
                    "status": "succeeded",
                    "step": 1,
                    "algorithm_id": "algo.fusion.road.conflation.v7",
                    "data_source_id": "catalog.flood.road",
                    "effective_algorithm_id": "algo.fusion.road.conflation.v7",
                },
            ),
            RunEvent(
                timestamp="2026-04-21T00:00:07+00:00",
                kind="step_failed",
                phase=RunPhase.running,
                message="step failed",
                current_step=2,
                details={
                    "status": "failed",
                    "step": 2,
                    "algorithm_id": "algo.fusion.water_polygon.priority_merge.v2",
                    "data_source_id": "catalog.flood.water",
                    "error": "RuntimeError: primary failed",
                },
            ),
        ]
    )

    assert [(step["step_name"], step["status"]) for step in trace["steps"]] == [
        ("step_started", "started"),
        ("step_succeeded", "succeeded"),
        ("step_failed", "failed"),
    ]
    assert trace["steps"][0]["input"] == {
        "step": 1,
        "algorithm_id": "algo.fusion.road.conflation.v7",
        "data_source_id": "catalog.flood.road",
    }
    assert trace["steps"][1]["output"] == {"effective_algorithm_id": "algo.fusion.road.conflation.v7"}
    assert trace["steps"][2]["output"] == {"error": "RuntimeError: primary failed"}


def _make_audit_events_for_successful_road_run() -> list[RunEvent]:
    return [
        RunEvent(timestamp="2026-04-21T00:00:00+00:00", kind="aoi_resolved", phase=RunPhase.planning, message="aoi"),
        RunEvent(timestamp="2026-04-21T00:00:01+00:00", kind="target_crs_resolved", phase=RunPhase.planning, message="crs"),
        RunEvent(
            timestamp="2026-04-21T00:00:02+00:00",
            kind="plan_created",
            phase=RunPhase.validating,
            message="plan",
            details={"workflow_id": "wf_road", "planning_mode": "task_driven", "planning_source": "llm"},
        ),
        RunEvent(timestamp="2026-04-21T00:00:03+00:00", kind="plan_validated", phase=RunPhase.running, message="valid"),
        RunEvent(timestamp="2026-04-21T00:00:04+00:00", kind="task_inputs_resolved", phase=RunPhase.running, message="inputs"),
        RunEvent(timestamp="2026-04-21T00:00:05+00:00", kind="execution_completed", phase=RunPhase.running, message="exec"),
        RunEvent(timestamp="2026-04-21T00:00:06+00:00", kind="run_succeeded", phase=RunPhase.succeeded, message="ok"),
    ]
