from __future__ import annotations

from schemas.agent import RunTrigger, RunTriggerType, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from schemas.plan_grounding import PlanGroundingGateDecision
from services.plan_grounding_service import build_plan_grounding_report, evaluate_plan_grounding_gate


def _plan(
    *,
    algorithm_id: str = "algo.fusion.building.v1",
    input_type: str = "dt.building.bundle",
    data_source_id: str = "catalog.flood.building",
    output_type: str = "dt.building.fused",
    expected_output_type: str | None = "dt.building.fused",
    retrieval: dict | None = None,
) -> WorkflowPlan:
    context = {
        "intent": {},
        "retrieval": retrieval
        or {
            "candidate_patterns": [
                {
                    "pattern_id": "wp.flood.building.default",
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
            "data_sources": [{"source_id": "catalog.flood.building"}],
            "algorithms": {"algo.fusion.building.v1": {"tool_ref": "builtin:building"}},
            "output_schema_policies": {"dt.building.fused": {"policy_id": "schema.building.fused"}},
        },
    }
    if expected_output_type is not None:
        context["intent"]["expected_output_type"] = expected_output_type
    return WorkflowPlan(
        workflow_id="wf-grounding",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building fusion"),
        context=context,
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id=algorithm_id,
                input=WorkflowTaskInput(data_type_id=input_type, data_source_id=data_source_id),
                output=WorkflowTaskOutput(data_type_id=output_type),
            )
        ],
        expected_output="building result",
    )


def test_algorithm_in_candidate_pattern_is_grounded() -> None:
    report = build_plan_grounding_report(_plan())

    assert report["grounded"] is True
    assert report["grounded_step_count"] == 1
    assert report["total_step_count"] == 1
    assert report["grounding_score"] == 1.0
    step = report["steps"][0]
    assert step["algorithm_id"] == "algo.fusion.building.v1"
    assert step["input_data_type"] == "dt.building.bundle"
    assert step["algorithm_grounded"] is True
    assert step["algorithm_known"] is True
    assert step["data_source_known"] is True
    assert step["output_type_matches_intent"] is True
    assert step["schema_policy_known"] is True
    assert step["pattern_ids"] == ["wp.flood.building.default"]
    assert step["issue_codes"] == []
    assert step["evidence_refs"] == [
        "plan.task(step=1).algorithm_id",
        "plan.task(step=1).input.data_type_id",
        "plan.task(step=1).input.data_source_id",
        "plan.task(step=1).output.data_type_id",
        "context.retrieval.candidate_patterns",
        "context.retrieval.data_sources",
        "context.retrieval.output_schema_policies",
        "context.intent.expected_output_type",
    ]


def test_algorithm_not_in_candidate_pattern_reports_issue() -> None:
    retrieval = {
        "candidate_patterns": [
            {
                "pattern_id": "wp.flood.building.default",
                "steps": [{"algorithm_id": "algo.fusion.building.v1", "data_source_id": "catalog.flood.building"}],
            }
        ],
        "data_sources": [{"source_id": "catalog.flood.building"}],
        "algorithms": {"algo.fusion.building.safe": {"tool_ref": "builtin:building_safe"}},
        "output_schema_policies": {"dt.building.fused": {"policy_id": "schema.building.fused"}},
    }

    report = build_plan_grounding_report(_plan(algorithm_id="algo.fusion.building.safe", retrieval=retrieval))

    step = report["steps"][0]
    assert report["grounded"] is False
    assert step["algorithm_known"] is True
    assert step["algorithm_grounded"] is False
    assert "ALGORITHM_NOT_IN_CANDIDATE_PATTERNS" in step["issue_codes"]


def test_data_source_not_in_retrieval_reports_issue() -> None:
    report = build_plan_grounding_report(_plan(data_source_id="catalog.unknown.building"))

    step = report["steps"][0]
    assert report["grounded"] is False
    assert step["data_source_known"] is False
    assert "DATA_SOURCE_NOT_IN_RETRIEVAL" in step["issue_codes"]


def test_candidate_pattern_joint_mismatch_does_not_count_as_grounded() -> None:
    retrieval = {
        "candidate_patterns": [
            {
                "pattern_id": "wp.flood.building.default",
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
            {"source_id": "catalog.flood.building"},
            {"source_id": "catalog.alt.building"},
        ],
        "algorithms": {"algo.fusion.building.v1": {"tool_ref": "builtin:building"}},
        "output_schema_policies": {"dt.building.fused": {"policy_id": "schema.building.fused"}},
    }

    report = build_plan_grounding_report(
        _plan(data_source_id="catalog.alt.building", retrieval=retrieval)
    )

    step = report["steps"][0]
    assert step["algorithm_grounded"] is True
    assert step["data_source_known"] is True
    assert report["grounded"] is False
    assert report["grounded_step_count"] == 0
    assert "CANDIDATE_PATTERN_STEP_MISMATCH" in step["issue_codes"]


def test_input_type_mismatch_does_not_count_as_grounded() -> None:
    report = build_plan_grounding_report(_plan(input_type="dt.raw.vector"))

    step = report["steps"][0]
    assert step["algorithm_grounded"] is True
    assert step["data_source_known"] is True
    assert report["grounded"] is False
    assert report["grounded_step_count"] == 0
    assert "CANDIDATE_PATTERN_STEP_MISMATCH" in step["issue_codes"]


def test_output_type_mismatch_reports_issue_when_intent_declares_expected_type() -> None:
    report = build_plan_grounding_report(
        _plan(output_type="dt.road.fused", expected_output_type="dt.building.fused")
    )

    step = report["steps"][0]
    assert report["grounded"] is False
    assert step["output_type_matches_intent"] is False
    assert "OUTPUT_TYPE_MISMATCH" in step["issue_codes"]


def test_missing_expected_output_type_is_compatible() -> None:
    report = build_plan_grounding_report(_plan(expected_output_type=None))

    assert report["grounded"] is True
    assert report["steps"][0]["output_type_matches_intent"] is True
    assert "OUTPUT_TYPE_MISMATCH" not in report["steps"][0]["issue_codes"]


def test_plan_grounding_gate_decision_serializes_rejection() -> None:
    decision = PlanGroundingGateDecision(
        mode="enforce",
        allowed=False,
        reason_code="PLAN_GROUNDING_FAILED",
        issue_codes=["DATA_SOURCE_NOT_IN_RETRIEVAL"],
    )

    payload = decision.model_dump(mode="json")

    assert payload["allowed"] is False
    assert payload["reason_code"] == "PLAN_GROUNDING_FAILED"


def test_grounding_gate_allows_report_mode_when_ungrounded() -> None:
    decision = evaluate_plan_grounding_gate(
        {"grounded": False, "grounding_score": 0.0, "steps": [{"issue_codes": ["DATA_SOURCE_NOT_IN_RETRIEVAL"]}]},
        mode="report",
    )

    assert decision.allowed is True
    assert decision.reason_code is None


def test_grounding_gate_rejects_enforce_mode_when_ungrounded() -> None:
    decision = evaluate_plan_grounding_gate(
        {"grounded": False, "grounding_score": 0.0, "steps": [{"issue_codes": ["DATA_SOURCE_NOT_IN_RETRIEVAL"]}]},
        mode="enforce",
    )

    assert decision.allowed is False
    assert decision.reason_code == "PLAN_GROUNDING_FAILED"
    assert decision.issue_codes == ["DATA_SOURCE_NOT_IN_RETRIEVAL"]
