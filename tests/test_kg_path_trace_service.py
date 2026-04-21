from schemas.agent import RunTrigger, RunTriggerType, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from services.kg_path_trace_service import build_kg_path_trace


def test_build_kg_path_trace_renders_relationship_chain() -> None:
    plan = WorkflowPlan(
        workflow_id="wf-kg",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="earthquake in Parakou"),
        context={
            "retrieval": {
                "candidate_patterns": [{"pattern_id": "wp.earthquake.building", "pattern_name": "Earthquake Building"}],
                "data_sources": [{"source_id": "catalog.earthquake.building", "source_name": "OSM + Microsoft"}],
            }
        },
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="fusion",
                algorithm_id="algo.fusion.building.v1",
                input=WorkflowTaskInput(data_type_id="dt.building.bundle", data_source_id="catalog.earthquake.building"),
                output=WorkflowTaskOutput(data_type_id="dt.building.fused"),
            )
        ],
        expected_output="building result",
    )

    trace = build_kg_path_trace(plan)

    assert trace["selected_pattern_id"] == "wp.earthquake.building"
    assert trace["chains"][0]["nodes"][0]["kind"] == "trigger"
    assert trace["chains"][0]["edges"][0]["relationship"] == "selects_pattern"
    assert any(node["id"] == "catalog.earthquake.building" for node in trace["chains"][0]["nodes"])
