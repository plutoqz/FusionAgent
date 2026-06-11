from __future__ import annotations

from typing import Any

from agent.planner import WorkflowPlanner
from kg.inmemory_repository import InMemoryKGRepository
from kg.models import PatternStep, WorkflowPatternNode
from llm.providers.base import LLMProvider
from llm.providers.mock_provider import MockLLMProvider
from schemas.agent import (
    RunTrigger,
    RunTriggerType,
    WorkflowPlan,
    WorkflowTask,
    WorkflowTaskInput,
    WorkflowTaskOutput,
)
from schemas.fusion import JobType


class FailingProvider(LLMProvider):
    def __init__(self) -> None:
        self.model = "failing-model"

    def generate_workflow_plan(self, system_prompt: str, context: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("simulated planning failure")


def _deprecated_pattern() -> WorkflowPatternNode:
    return WorkflowPatternNode(
        pattern_id="wp.deprecated.road",
        pattern_name="Deprecated Road",
        job_type=JobType.road,
        disaster_types=["generic"],
        success_rate=0.99,
        steps=[
            PatternStep(
                order=1,
                name="deprecated_road",
                algorithm_id="algo.fusion.road.v1",
                input_data_type="dt.road.bundle",
                output_data_type="dt.road.fused",
                data_source_id="catalog.flood.road",
            )
        ],
    )


def test_planner_fallback_skips_deprecated_high_score_pattern() -> None:
    repo = InMemoryKGRepository(patterns=[_deprecated_pattern(), *InMemoryKGRepository().patterns])
    planner = WorkflowPlanner(repo, FailingProvider())

    plan = planner.create_plan(
        run_id="run-planner-contract",
        job_type=JobType.road,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="road"),
    )

    assert plan.context["planning_source"] == "kg_fallback"
    assert plan.tasks[0].algorithm_id == "algo.fusion.road.conflation.v7"
    assert plan.context["runtime_contract"]["skipped_fallback_patterns"][0]["pattern_id"] == "wp.deprecated.road"


def test_planner_fallback_runtime_contract_metadata_does_not_mutate_kg_patterns() -> None:
    repo = InMemoryKGRepository(patterns=[_deprecated_pattern(), *InMemoryKGRepository().patterns])
    planner = WorkflowPlanner(repo, FailingProvider())

    planner.create_plan(
        run_id="run-planner-contract-metadata",
        job_type=JobType.road,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="road"),
    )

    assert all("_runtime_contract_skipped_patterns" not in pattern.metadata for pattern in repo.patterns)


def test_planner_finalize_filters_deprecated_alternatives() -> None:
    repo = InMemoryKGRepository()
    planner = WorkflowPlanner(repo, MockLLMProvider())
    plan = WorkflowPlan(
        workflow_id="wf-alt-filter",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="road"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="road",
                description="road",
                algorithm_id="algo.fusion.road.conflation.v7",
                input=WorkflowTaskInput(data_type_id="dt.road.bundle", data_source_id="catalog.flood.road"),
                output=WorkflowTaskOutput(data_type_id="dt.road.fused"),
                alternatives=["algo.fusion.road.v1", "algo.fusion.road.conflation.v7"],
            )
        ],
        expected_output="road",
    )

    finalized = planner._finalize_plan(plan)

    assert "algo.fusion.road.v1" not in finalized.tasks[0].alternatives
    assert finalized.context["runtime_contract"]["skipped_alternatives"][0]["algorithm_id"] == "algo.fusion.road.v1"
