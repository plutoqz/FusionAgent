import pytest

from agent.intent_resolver import resolve_planning_mode
from kg.knowledge_release import KnowledgeReleaseError
from schemas.agent import RunTrigger, RunTriggerType


def test_resolve_planning_mode_prefers_scenario_when_disaster_type_present() -> None:
    trigger = RunTrigger(
        type=RunTriggerType.disaster_event,
        content="flood response for building fusion",
        disaster_type="flood",
    )
    resolved = resolve_planning_mode(trigger)
    assert resolved["planning_mode"] == "scenario_driven"


def test_resolve_planning_mode_prefers_task_when_user_specifies_data_request() -> None:
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need building and road data for Gilgit, Pakistan",
    )
    resolved = resolve_planning_mode(trigger)
    assert resolved["planning_mode"] == "task_driven"
    assert resolved["profile_source"] == "direct_task"


def test_resolve_planning_mode_uses_kg_default_when_no_task_semantic_matches() -> None:
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="prepare data for Gilgit, Pakistan",
    )

    resolved = resolve_planning_mode(trigger)

    assert resolved == {"planning_mode": "task_driven", "profile_source": "default_task"}


def test_resolve_planning_mode_rejects_disaster_outside_frozen_vocabulary() -> None:
    trigger = RunTrigger(
        type=RunTriggerType.disaster_event,
        content="wildfire response",
        disaster_type="wildfire",
    )

    with pytest.raises(KnowledgeReleaseError, match="outside the frozen KG vocabulary"):
        resolve_planning_mode(trigger)
