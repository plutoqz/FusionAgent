from __future__ import annotations

import pytest

from kg.knowledge_release import KnowledgeReleaseError
from schemas.agent import RunTrigger, RunTriggerType, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from services.agent_run_service import AgentRunService


class _MissingSchemaRepository:
    @staticmethod
    def get_output_schema_policy(_output_data_type: str):
        return None


def _plan_without_schema_policy() -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id="wf.missing.schema",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="test"),
        expected_output="unknown",
        tasks=[
            WorkflowTask(
                step=1,
                name="unknown",
                description="unknown output",
                algorithm_id="algo.test",
                input=WorkflowTaskInput(data_type_id="dt.input", data_source_id="raw.input"),
                output=WorkflowTaskOutput(data_type_id="dt.unknown.output"),
            )
        ],
    )


def test_research_runtime_fails_closed_without_output_schema_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEOFUSION_KG_RUNTIME_MODE", "research")
    service = object.__new__(AgentRunService)
    service.kg_repo = _MissingSchemaRepository()

    with pytest.raises(RuntimeError, match="Frozen KG output schema policy is required"):
        service._required_fields_for_plan(_plan_without_schema_policy())


def test_explicit_disaster_outside_frozen_vocabulary_fails_closed() -> None:
    plan = _plan_without_schema_policy().model_copy(
        update={
            "trigger": RunTrigger(
                type=RunTriggerType.disaster_event,
                content="wildfire response",
                disaster_type="wildfire",
            )
        }
    )

    with pytest.raises(KnowledgeReleaseError, match="outside the frozen KG vocabulary"):
        AgentRunService._plan_disaster_type(plan)


@pytest.mark.parametrize("content", ["wildfire response", "hurricane response", "conflict response"])
def test_implicit_unsupported_disaster_text_fails_closed(content: str) -> None:
    plan = _plan_without_schema_policy().model_copy(
        update={
            "trigger": RunTrigger(
                type=RunTriggerType.disaster_event,
                content=content,
            )
        }
    )

    with pytest.raises(KnowledgeReleaseError, match="outside the frozen KG vocabulary"):
        AgentRunService._plan_disaster_type(plan)


def test_untyped_disaster_event_fails_closed() -> None:
    plan = _plan_without_schema_policy().model_copy(
        update={
            "trigger": RunTrigger(
                type=RunTriggerType.disaster_event,
                content="major incident response",
            )
        }
    )

    with pytest.raises(KnowledgeReleaseError, match="no type recognized"):
        AgentRunService._plan_disaster_type(plan)


def test_known_disaster_without_compatible_or_generic_source_does_not_fail_open() -> None:
    plan = _plan_without_schema_policy().model_copy(
        update={
            "trigger": RunTrigger(
                type=RunTriggerType.disaster_event,
                content="flood response",
                disaster_type="flood",
            )
        }
    )
    sources = [
        {
            "source_id": "catalog.earthquake.only",
            "disaster_types": ["earthquake"],
            "metadata": {},
        }
    ]

    assert AgentRunService._filter_disaster_compatible_sources(sources, plan) == []
