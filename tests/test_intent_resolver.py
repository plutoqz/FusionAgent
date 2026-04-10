from agent.intent_resolver import resolve_planning_mode
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
