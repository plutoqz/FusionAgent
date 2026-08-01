from __future__ import annotations

import pytest

from schemas.agent import (
    ProductContractRef,
    RunCreateRequest,
    RunTrigger,
    RunTriggerType,
    WorkflowPlan,
    WorkflowTask,
    WorkflowTaskInput,
    WorkflowTaskOutput,
)
from schemas.fusion import JobType
from schemas.task_kind import TaskKind
from services.task_kind_resolution_service import resolve_task_kind


def _waterways_request(*, preferred_pattern_id: str | None = None) -> RunCreateRequest:
    return RunCreateRequest(
        job_type=JobType.water,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="Fuse waterways"),
        preferred_pattern_id=preferred_pattern_id,
    )


def _waterways_plan() -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id="wf.waterways.test",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="Fuse waterways"),
        expected_output="waterways",
        tasks=[
            WorkflowTask(
                step=1,
                task_id="task.waterways.fusion",
                name="waterways",
                description="waterways fusion",
                algorithm_id="algo.fusion.waterways.v7",
                input=WorkflowTaskInput(
                    data_type_id="dt.waterways.bundle",
                    data_source_id="catalog.flood.waterways",
                ),
                output=WorkflowTaskOutput(data_type_id="dt.waterways.fused"),
            )
        ],
    )


def test_plan_resolves_waterways_without_preferred_pattern() -> None:
    assert resolve_task_kind(request=_waterways_request(), plan=_waterways_plan()) is TaskKind.waterways


def test_request_pattern_cannot_override_frozen_plan_semantics() -> None:
    with pytest.raises(ValueError, match="Task-kind evidence conflicts"):
        resolve_task_kind(
            request=_waterways_request(preferred_pattern_id="wp.flood.water_polygon.default"),
            plan=_waterways_plan(),
        )


def test_product_contract_cannot_conflict_with_frozen_plan_semantics() -> None:
    plan = _waterways_plan().model_copy(
        update={
            "product_contract": ProductContractRef(
                contract_id="contract.product.road.v1",
                contract_name="Road contract",
                product_type="road_multi_source_vector_fusion",
            )
        }
    )

    with pytest.raises(ValueError, match="Task-kind evidence conflicts"):
        resolve_task_kind(request=_waterways_request(), plan=plan)
