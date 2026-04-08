from agent.parameter_binding import bind_plan_parameters
from agent.planner import WorkflowPlanner
from kg.inmemory_repository import InMemoryKGRepository
from llm.providers.base import LLMProvider
from schemas.agent import RunTrigger, RunTriggerType, WorkflowPlan
from schemas.fusion import JobType


def test_bind_plan_parameters_injects_kg_defaults_and_preserves_explicit_override() -> None:
    repo = InMemoryKGRepository()
    plan = WorkflowPlan.model_validate(
        {
            "workflow_id": "wf_bind_defaults",
            "trigger": {"type": "user_query", "content": "building"},
            "context": {},
            "tasks": [
                {
                    "step": 1,
                    "name": "building_fusion",
                    "description": "execute building fusion",
                    "algorithm_id": "algo.fusion.building.v1",
                    "input": {
                        "data_type_id": "dt.building.bundle",
                        "data_source_id": "upload.bundle",
                        "parameters": {
                            "match_similarity_threshold": 0.55
                        },
                    },
                    "output": {"data_type_id": "dt.building.fused", "description": "out"},
                    "depends_on": [],
                    "is_transform": False,
                    "kg_validated": True,
                    "alternatives": [],
                },
                {
                    "step": 2,
                    "name": "road_fusion_safe",
                    "description": "execute road fusion",
                    "algorithm_id": "algo.fusion.road.safe",
                    "input": {
                        "data_type_id": "dt.road.bundle",
                        "data_source_id": "upload.bundle",
                        "parameters": {},
                    },
                    "output": {"data_type_id": "dt.road.fused", "description": "out"},
                    "depends_on": [],
                    "is_transform": False,
                    "kg_validated": True,
                    "alternatives": [],
                },
            ],
            "expected_output": "out",
        }
    )

    bound = bind_plan_parameters(plan, repo)

    building_params = bound.tasks[0].input.parameters
    road_params = bound.tasks[1].input.parameters

    assert building_params["match_similarity_threshold"] == 0.55
    assert building_params["one_to_one_min_overlap_similarity"] == 0.3
    assert road_params["max_hausdorff_m"] == 10.0
    assert road_params["dedupe_buffer_m"] == 12.0


class _PlannerProvider(LLMProvider):
    def __init__(self, *, match_similarity_threshold: float, workflow_id: str = "wf_bind_defaults") -> None:
        self.match_similarity_threshold = match_similarity_threshold
        self.workflow_id = workflow_id

    def generate_workflow_plan(self, system_prompt: str, context: dict) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "trigger": context["intent"]["trigger"],
            "context": {},
            "tasks": [
                {
                    "step": 1,
                    "name": "building_fusion",
                    "description": "execute building fusion",
                    "algorithm_id": "algo.fusion.building.v1",
                    "input": {
                        "data_type_id": "dt.building.bundle",
                        "data_source_id": "upload.bundle",
                        "parameters": {"match_similarity_threshold": self.match_similarity_threshold},
                    },
                    "output": {"data_type_id": "dt.building.fused", "description": "out"},
                    "depends_on": [],
                    "is_transform": False,
                    "kg_validated": True,
                    "alternatives": [],
                }
            ],
            "expected_output": "out",
        }


def test_workflow_planner_create_plan_binds_kg_defaults() -> None:
    repo = InMemoryKGRepository()
    planner = WorkflowPlanner(repo, _PlannerProvider(match_similarity_threshold=0.52))
    plan = planner.create_plan(
        run_id="run_bind_defaults",
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
    )

    params = plan.tasks[0].input.parameters
    assert params["match_similarity_threshold"] == 0.52
    assert params["one_to_one_min_overlap_similarity"] == 0.3


def test_workflow_planner_replan_binds_kg_defaults() -> None:
    repo = InMemoryKGRepository()
    planner = WorkflowPlanner(repo, _PlannerProvider(match_similarity_threshold=0.61, workflow_id="wf_replanned"))
    previous = WorkflowPlan.model_validate(
        {
            "workflow_id": "wf_previous",
            "trigger": {"type": "user_query", "content": "building"},
            "context": {"plan_revision": 1},
            "tasks": [
                {
                    "step": 1,
                    "name": "building_fusion",
                    "description": "execute building fusion",
                    "algorithm_id": "algo.fusion.building.v1",
                    "input": {
                        "data_type_id": "dt.building.bundle",
                        "data_source_id": "upload.bundle",
                        "parameters": {"match_similarity_threshold": 0.52},
                    },
                    "output": {"data_type_id": "dt.building.fused", "description": "out"},
                    "depends_on": [],
                    "is_transform": False,
                    "kg_validated": True,
                    "alternatives": [],
                }
            ],
            "expected_output": "out",
        }
    )

    plan = planner.replan_from_error(
        run_id="run_bind_defaults",
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        previous_plan=previous,
        failed_step=1,
        error_message="exhausted repairs",
    )

    params = plan.tasks[0].input.parameters
    assert params["match_similarity_threshold"] == 0.61
    assert params["one_to_one_min_overlap_similarity"] == 0.3
    assert plan.context["plan_revision"] == 2
