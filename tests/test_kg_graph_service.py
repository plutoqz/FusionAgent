from __future__ import annotations

from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import RunTrigger, RunTriggerType, ValidationReport, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from services.kg_graph_service import build_overview_graph, build_run_path_graph


def _build_plan() -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id="wf-kg-graph",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="need building data"),
        context={
            "retrieval": {
                "candidate_patterns": [
                    {
                        "pattern_id": "wp.flood.building.default",
                        "pattern_name": "Flood Building Default",
                        "steps": [
                            {
                                "algorithm_id": "algo.fusion.building.v1",
                                "input_data_type": "dt.building.bundle",
                                "output_data_type": "dt.building.fused",
                                "data_source_id": "catalog.flood.building",
                            }
                        ],
                    }
                ],
                "data_sources": [
                    {
                        "source_id": "catalog.flood.building",
                        "source_name": "Flood Building Bundle",
                    }
                ],
                "algorithms": {
                    "algo.fusion.building.v1": {
                        "tool_ref": "adapters.building_adapter:run_building_fusion",
                    }
                },
                "output_schema_policies": {
                    "dt.building.fused": {
                        "policy_id": "schema.building.fused",
                    }
                },
            },
            "grounding_report": {
                "grounded": True,
                "grounded_step_count": 1,
                "total_step_count": 1,
                "grounding_score": 1.0,
                "steps": [
                    {
                        "step": 1,
                        "algorithm_id": "algo.fusion.building.v1",
                        "input_data_type": "dt.building.bundle",
                        "data_source_id": "catalog.flood.building",
                        "output_data_type": "dt.building.fused",
                        "algorithm_grounded": True,
                        "algorithm_known": True,
                        "data_source_known": True,
                        "output_type_matches_intent": True,
                        "schema_policy_known": True,
                        "pattern_ids": ["wp.flood.building.default"],
                        "issue_codes": [],
                        "evidence_refs": ["plan.task(step=1).algorithm_id"],
                    }
                ],
            },
        },
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id="algo.fusion.building.v1",
                input=WorkflowTaskInput(
                    data_type_id="dt.building.bundle",
                    data_source_id="catalog.flood.building",
                    parameters={},
                ),
                output=WorkflowTaskOutput(data_type_id="dt.building.fused", description=""),
                depends_on=[],
                is_transform=False,
                kg_validated=True,
                alternatives=["algo.fusion.building.safe"],
            )
        ],
        expected_output="building result",
        validation=ValidationReport(valid=True, inserted_transform_steps=0, issues=[]),
    )


def test_build_overview_graph_exposes_patterns_algorithms_and_sources() -> None:
    graph = build_overview_graph(InMemoryKGRepository())

    node_kinds = {node.kind for node in graph.nodes}
    assert {"workflow_pattern", "algorithm", "data_source"} <= node_kinds
    assert any(node.id == "wp.flood.building.default" for node in graph.nodes)
    assert any(node.id == "algo.fusion.building.v1" for node in graph.nodes)
    assert any(node.id == "catalog.flood.building" for node in graph.nodes)
    assert any(
        edge.source == "wp.flood.building.default"
        and edge.target == "algo.fusion.building.v1"
        and edge.relationship == "uses_algorithm"
        for edge in graph.edges
    )
    assert any(edge.relationship == "uses_data_source" for edge in graph.edges)
    assert graph.meta["graph_type"] == "overview"


def test_build_run_path_graph_normalizes_trace_into_graph_response() -> None:
    graph = build_run_path_graph(_build_plan())

    nodes = {node.id: node for node in graph.nodes}
    assert graph.meta["graph_type"] == "run_path"
    assert graph.meta["workflow_id"] == "wf-kg-graph"
    assert graph.meta["selected_pattern_id"] == "wp.flood.building.default"
    assert graph.meta["grounding_report"]["grounded"] is True
    assert nodes["wp.flood.building.default"].kind == "workflow_pattern"
    assert nodes["task:1"].kind == "task"
    assert nodes["catalog.flood.building"].kind == "data_source"
    assert nodes["algo.fusion.building.v1"].kind == "algorithm"
    assert any(
        edge.source == "catalog.flood.building"
        and edge.target == "algo.fusion.building.v1"
        and edge.relationship == "executes_algorithm"
        for edge in graph.edges
    )
