from agent.validator import WorkflowValidator
from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import (
    RunTrigger,
    RunTriggerType,
    ValidationIssue,
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


def test_validator_rejects_task_not_activated_by_effective_scenario_profile() -> None:
    plan = WorkflowPlan(
        workflow_id="wf_profile_task_mismatch",
        trigger=RunTrigger(type=RunTriggerType.disaster_event, content="flood building fusion", disaster_type="flood"),
        context={
            "intent": {
                "job_type": "building",
                "effective_scenario_profile_id": "scenario.flood.default",
                "effective_activated_tasks": ["task.road.fusion"],
            }
        },
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id="algo.fusion.building.v1",
                input=WorkflowTaskInput(
                    data_type_id="dt.building.bundle",
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
    assert fixed.validation.issues[0].code == "SCENARIO_PROFILE_TASK_MISMATCH"


def test_validator_marks_deprecated_algorithm_with_runtime_contract_issue() -> None:
    plan = WorkflowPlan(
        workflow_id="wf_deprecated_algo",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="road"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="deprecated_road",
                description="deprecated road",
                algorithm_id="algo.fusion.road.v1",
                input=WorkflowTaskInput(
                    data_type_id="dt.road.bundle",
                    data_source_id="catalog.flood.road",
                    parameters={},
                ),
                output=WorkflowTaskOutput(data_type_id="dt.road.fused", description=""),
            )
        ],
        expected_output="road result",
    )

    fixed = WorkflowValidator(InMemoryKGRepository()).validate_and_repair(plan)

    assert fixed.validation is not None
    assert fixed.validation.valid is False
    assert fixed.validation.issues[0].code == "DEPRECATED_ALGORITHM"
    assert fixed.validation.rejected is False
    assert fixed.validation.enforcement_mode == "report"
    assert fixed.tasks[0].kg_validated is False


def test_validator_enforce_mode_marks_report_rejected() -> None:
    plan = WorkflowPlan(
        workflow_id="wf_enforce_deprecated",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="road"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="deprecated_road",
                description="deprecated road",
                algorithm_id="algo.fusion.road.v1",
                input=WorkflowTaskInput(
                    data_type_id="dt.road.bundle",
                    data_source_id="catalog.flood.road",
                    parameters={},
                ),
                output=WorkflowTaskOutput(data_type_id="dt.road.fused", description=""),
            )
        ],
        expected_output="road result",
    )

    fixed = WorkflowValidator(InMemoryKGRepository(), enforcement_mode="enforce").validate_and_repair(plan)

    assert fixed.validation is not None
    assert fixed.validation.valid is False
    assert fixed.validation.rejected is True
    assert fixed.validation.enforcement_mode == "enforce"
