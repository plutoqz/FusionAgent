from agent.retriever import PlanningContextBuilder
from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import RunTrigger, RunTriggerType
from schemas.fusion import JobType


def test_retrieval_payload_contains_task_bundle_for_task_driven_request() -> None:
    builder = PlanningContextBuilder(InMemoryKGRepository())
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need building and road data for Gilgit, Pakistan",
    )

    context, _reason = builder.build(job_type=JobType.building, trigger=trigger)

    assert "task_bundle" in context["intent"]
    assert context["intent"]["task_bundle"]["bundle_id"] == "task_bundle.direct_request"
