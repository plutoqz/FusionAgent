from agent.parameter_binding import bind_plan_parameters
from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import WorkflowPlan


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
