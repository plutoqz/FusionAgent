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


def test_validator_inserts_transform_steps() -> None:
    plan = WorkflowPlan(
        workflow_id="wf_test",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="test"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id="algo.fusion.building.v1",
                input=WorkflowTaskInput(data_type_id="dt.raw.vector", data_source_id="upload.bundle", parameters={}),
                output=WorkflowTaskOutput(data_type_id="dt.building.fused", description=""),
                depends_on=[],
                is_transform=False,
                kg_validated=False,
                alternatives=[],
            )
        ],
        expected_output="building result",
    )

    validator = WorkflowValidator(InMemoryKGRepository())
    fixed = validator.validate_and_repair(plan)

    assert fixed.validation is not None
    assert fixed.validation.valid is True
    assert fixed.validation.inserted_transform_steps == 1
    assert len(fixed.tasks) == 2
    assert fixed.tasks[0].is_transform is True
    assert fixed.tasks[1].kg_validated is True

