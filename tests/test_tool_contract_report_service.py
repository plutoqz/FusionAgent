from __future__ import annotations

from services.tool_contract_report_service import build_tool_contract_report
from schemas.agent import (
    RunTrigger,
    RunTriggerType,
    WorkflowPlan,
    WorkflowTask,
    WorkflowTaskInput,
    WorkflowTaskOutput,
)


def _plan(
    *,
    algorithm_id: str = "algo.fusion.building.v1",
    output_type: str = "dt.building.fused",
) -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id="wf-tool-contract",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="need building data"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id=algorithm_id,
                input=WorkflowTaskInput(
                    data_type_id="dt.building.bundle",
                    data_source_id="catalog.flood.building",
                ),
                output=WorkflowTaskOutput(data_type_id=output_type),
                is_transform=False,
                kg_validated=True,
            )
        ],
        expected_output="building result",
    )


def test_tool_contract_report_marks_registered_task_as_valid() -> None:
    report = build_tool_contract_report(_plan())

    assert report["valid"] is True
    assert report["known_step_count"] == 1
    assert report["total_step_count"] == 1
    assert report["steps"][0]["algorithm_id"] == "algo.fusion.building.v1"
    assert report["steps"][0]["handler_name"] == "_handle_building"
    assert report["steps"][0]["input_types"] == ["dt.building.bundle"]
    assert report["steps"][0]["output_type"] == "dt.building.fused"
    assert report["steps"][0]["issue_codes"] == []


def test_tool_contract_report_flags_unknown_algorithm() -> None:
    report = build_tool_contract_report(_plan(algorithm_id="algo.fusion.unknown.v1"))

    assert report["valid"] is False
    assert report["known_step_count"] == 0
    assert report["steps"][0]["issue_codes"] == ["UNKNOWN_TOOL"]


def test_tool_contract_report_flags_output_type_mismatch() -> None:
    report = build_tool_contract_report(_plan(output_type="dt.road.fused"))

    assert report["valid"] is False
    assert "TOOL_OUTPUT_TYPE_MISMATCH" in report["steps"][0]["issue_codes"]


def test_tool_contract_report_marks_reserved_trajectory_transform() -> None:
    plan = _plan(
        algorithm_id="algo.transform.trajectory_to_road_candidate",
        output_type="dt.road.candidate",
    )
    plan.tasks[0].is_transform = True
    plan.tasks[0].input.data_type_id = "dt.trajectory.raw"

    report = build_tool_contract_report(plan)

    assert report["valid"] is True
    assert report["steps"][0]["reserved"] is True
    assert report["steps"][0]["issue_codes"] == ["RESERVATION_ONLY_TOOL"]
