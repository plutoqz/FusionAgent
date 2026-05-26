from schemas.agent import RunTrigger, RunTriggerType, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from services.kg_path_trace_service import build_kg_path_trace


def test_build_kg_path_trace_renders_relationship_chain() -> None:
    plan = WorkflowPlan(
        workflow_id="wf-kg",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="earthquake in Parakou"),
        context={
            "retrieval": {
                "candidate_patterns": [
                    {
                        "pattern_id": "wp.earthquake.building",
                        "pattern_name": "Earthquake Building",
                        "steps": [
                            {
                                "algorithm_id": "algo.fusion.building.v1",
                                "input_data_type": "dt.building.bundle",
                                "output_data_type": "dt.building.fused",
                                "data_source_id": "catalog.earthquake.building",
                            }
                        ],
                    }
                ],
                "data_sources": [{"source_id": "catalog.earthquake.building", "source_name": "OSM + Microsoft"}],
                "algorithms": {"algo.fusion.building.v1": {"tool_ref": "builtin:building"}},
                "output_schema_policies": {"dt.building.fused": {"policy_id": "schema.building.fused"}},
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
    assert trace["grounding_report"]["grounded"] is True
    assert trace["grounding_report"]["steps"][0]["algorithm_grounded"] is True


def test_build_kg_path_trace_recomputes_stale_cached_grounding_report() -> None:
    plan = WorkflowPlan(
        workflow_id="wf-kg-stale",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="earthquake in Parakou"),
        context={
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
                        "algorithm_grounded": True,
                        "algorithm_known": True,
                        "data_source_known": True,
                        "output_type_matches_intent": True,
                        "schema_policy_known": True,
                        "pattern_ids": ["wp.earthquake.building"],
                        "issue_codes": [],
                        "evidence_refs": ["plan.task(step=1).algorithm_id"],
                    }
                ],
            },
            "retrieval": {
                "candidate_patterns": [
                    {
                        "pattern_id": "wp.earthquake.building",
                        "pattern_name": "Earthquake Building",
                        "steps": [
                            {
                                "algorithm_id": "algo.fusion.building.v1",
                                "input_data_type": "dt.building.bundle",
                                "output_data_type": "dt.building.fused",
                                "data_source_id": "catalog.earthquake.building",
                            }
                        ],
                    }
                ],
                "data_sources": [{"source_id": "catalog.earthquake.building", "source_name": "OSM + Microsoft"}],
                "algorithms": {"algo.fusion.building.v1": {"tool_ref": "builtin:building"}},
                "output_schema_policies": {"dt.building.fused": {"policy_id": "schema.building.fused"}},
            },
        },
        tasks=[
            WorkflowTask(
                step=2,
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

    assert trace["chains"][0]["task_step"] == 2
    assert trace["grounding_report"]["steps"][0]["step"] == 2
    assert trace["grounding_report"]["steps"][0]["evidence_refs"][0] == "plan.task(step=2).algorithm_id"


def test_build_kg_path_trace_recomputes_cached_report_when_input_type_changes() -> None:
    plan = WorkflowPlan(
        workflow_id="wf-kg-stale-input",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="earthquake in Parakou"),
        context={
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
                        "data_source_id": "catalog.earthquake.building",
                        "output_data_type": "dt.building.fused",
                        "algorithm_grounded": True,
                        "algorithm_known": True,
                        "data_source_known": True,
                        "output_type_matches_intent": True,
                        "schema_policy_known": True,
                        "pattern_ids": ["wp.earthquake.building"],
                        "issue_codes": [],
                        "evidence_refs": ["plan.task(step=1).algorithm_id"],
                    }
                ],
            },
            "retrieval": {
                "candidate_patterns": [
                    {
                        "pattern_id": "wp.earthquake.building",
                        "pattern_name": "Earthquake Building",
                        "steps": [
                            {
                                "algorithm_id": "algo.fusion.building.v1",
                                "input_data_type": "dt.building.bundle",
                                "output_data_type": "dt.building.fused",
                                "data_source_id": "catalog.earthquake.building",
                            }
                        ],
                    }
                ],
                "data_sources": [{"source_id": "catalog.earthquake.building", "source_name": "OSM + Microsoft"}],
                "algorithms": {"algo.fusion.building.v1": {"tool_ref": "builtin:building"}},
                "output_schema_policies": {"dt.building.fused": {"policy_id": "schema.building.fused"}},
            },
        },
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="fusion",
                algorithm_id="algo.fusion.building.v1",
                input=WorkflowTaskInput(data_type_id="dt.raw.vector", data_source_id="catalog.earthquake.building"),
                output=WorkflowTaskOutput(data_type_id="dt.building.fused"),
            )
        ],
        expected_output="building result",
    )

    trace = build_kg_path_trace(plan)

    assert trace["grounding_report"]["grounded"] is False
    assert "CANDIDATE_PATTERN_STEP_MISMATCH" in trace["grounding_report"]["steps"][0]["issue_codes"]


def test_build_kg_path_trace_prefers_pattern_matching_actual_task_step() -> None:
    plan = WorkflowPlan(
        workflow_id="wf-road-fusioncode",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="need road data for Gilgit city, Pakistan"),
        context={
            "retrieval": {
                "candidate_patterns": [
                    {
                        "pattern_id": "wp.flood.road.default",
                        "pattern_name": "Flood Road Fusion",
                        "steps": [
                            {
                                "algorithm_id": "algo.fusion.road.conflation.v7",
                                "input_data_type": "dt.road.bundle",
                                "output_data_type": "dt.road.fused",
                                "data_source_id": "catalog.flood.road",
                            }
                        ],
                    },
                    {
                        "pattern_id": "wp.road.fusioncode.conflation.v7",
                        "pattern_name": "FusionCode V7 Road Conflation",
                        "steps": [
                            {
                                "algorithm_id": "algo.fusion.road.conflation.v7",
                                "input_data_type": "dt.road.bundle",
                                "output_data_type": "dt.road.fused",
                                "data_source_id": "upload.bundle",
                            }
                        ],
                    },
                ],
                "data_sources": [{"source_id": "upload.bundle", "source_name": "Uploaded Bundle"}],
                "algorithms": {
                    "algo.fusion.road.conflation.v7": {"tool_ref": "fusion_algorithms:_handle_road_conflation_v7"},
                },
                "output_schema_policies": {"dt.road.fused": {"policy_id": "schema.road.fused"}},
            },
        },
        tasks=[
            WorkflowTask(
                step=1,
                name="road_conflation_v7",
                description="fusion",
                algorithm_id="algo.fusion.road.conflation.v7",
                input=WorkflowTaskInput(data_type_id="dt.road.bundle", data_source_id="upload.bundle"),
                output=WorkflowTaskOutput(data_type_id="dt.road.fused"),
            )
        ],
        expected_output="road result",
    )

    trace = build_kg_path_trace(plan)

    assert trace["selected_pattern_id"] == "wp.road.fusioncode.conflation.v7"
