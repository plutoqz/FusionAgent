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


def test_validator_rejects_reservation_only_data_source() -> None:
    plan = WorkflowPlan(
        workflow_id="wf_reserved_source",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="test"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id="algo.fusion.building.v1",
                input=WorkflowTaskInput(
                    data_type_id="dt.raw.vector",
                    data_source_id="raw.openbuildingmap.building",
                    parameters={},
                ),
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
    assert fixed.validation.valid is False
    assert fixed.validation.issues[0].code == "UNSELECTABLE_DATA_SOURCE"
    assert fixed.tasks[0].kg_validated is False


def test_validator_rejects_reservation_only_algorithm() -> None:
    plan = WorkflowPlan(
        workflow_id="wf_reserved_algo",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="test"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="building_height_enrichment",
                description="reserved enrichment",
                algorithm_id="algo.enrich.building.height_from_raster.reserved",
                input=WorkflowTaskInput(
                    data_type_id="dt.raster.building_presence",
                    data_source_id="upload.bundle",
                    parameters={},
                ),
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
    assert fixed.validation.valid is False
    assert fixed.validation.issues[0].code == "RESERVED_ALGORITHM"
    assert fixed.tasks[0].kg_validated is False
