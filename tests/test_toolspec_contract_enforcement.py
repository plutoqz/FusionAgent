from __future__ import annotations

import pytest

from agent.tooling import build_default_tool_registry
from agent.validator import WorkflowValidator
from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import (
    RunTrigger,
    RunTriggerType,
    WorkflowPlan,
    WorkflowTask,
    WorkflowTaskInput,
    WorkflowTaskOutput,
)


def _plan_with_single_task(
    *,
    algorithm_id: str,
    input_type: str,
    output_type: str,
    parameters: dict[str, object] | None = None,
) -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id="wf_toolspec_contract",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="contract test"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="contract_test",
                description="contract enforcement test",
                algorithm_id=algorithm_id,
                input=WorkflowTaskInput(
                    data_type_id=input_type,
                    data_source_id="catalog.flood.building",
                    parameters=parameters or {},
                ),
                output=WorkflowTaskOutput(data_type_id=output_type, description=""),
                depends_on=[],
                is_transform=False,
                kg_validated=False,
                alternatives=[],
            )
        ],
        expected_output="contract enforcement",
    )


def test_executor_rejects_unknown_or_schema_invalid_tool() -> None:
    registry = build_default_tool_registry()

    with pytest.raises(ValueError, match="Unknown algorithm in tool registry"):
        registry.require("algo.unknown")


def test_validator_rejects_out_of_range_parameter_binding() -> None:
    plan = _plan_with_single_task(
        algorithm_id="algo.fusion.building.v1",
        input_type="dt.building.bundle",
        output_type="dt.building.fused",
        parameters={"match_similarity_threshold": 1.5},
    )

    fixed = WorkflowValidator(InMemoryKGRepository()).validate_and_repair(plan)

    assert fixed.validation is not None
    assert fixed.validation.valid is False
    assert any(issue.code == "PARAM_OUT_OF_RANGE" for issue in fixed.validation.issues)


def test_validator_rejects_tool_output_type_mismatch() -> None:
    plan = _plan_with_single_task(
        algorithm_id="algo.fusion.building.v1",
        input_type="dt.building.bundle",
        output_type="dt.road.fused",
    )

    fixed = WorkflowValidator(InMemoryKGRepository()).validate_and_repair(plan)

    assert fixed.validation is not None
    assert fixed.validation.valid is False
    assert any(issue.code == "TOOL_OUTPUT_TYPE_MISMATCH" for issue in fixed.validation.issues)
