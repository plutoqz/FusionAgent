from pathlib import Path

from schemas.research_case_manifest import load_research_case_manifest
from schemas.research_llm_pilot import ResearchPlanningDecision
from services.research_plan_evaluation import evaluate_research_plan


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def _case(case_id: str):
    manifest = load_research_case_manifest(MANIFEST)
    return next(case for case in manifest.cases if case.case_id == case_id)


def _plan(*, decision="partial", tasks=None):
    return ResearchPlanningDecision.model_validate(
        {
            "decision": decision,
            "tasks": tasks or [],
            "uncertainties": [],
            "evidence": [],
        }
    )


def _task(order, task_kind, state, source="source.ok"):
    return {
        "order": order,
        "task_kind": task_kind,
        "source_ids": [source],
        "algorithm_id": None,
        "delivery_state": state,
        "rationale": "structured test plan",
    }


def test_evaluator_accepts_exact_plan_and_keeps_manual_items_pending() -> None:
    result = evaluate_research_plan(
        _case("C01"),
        _plan(tasks=[_task(1, "road", "planned"), _task(2, "building", "gap")]),
        allowed_strings={"source.ok"},
    )

    assert result.automatic_score == 1.0
    assert result.task_metrics.f1 == 1.0
    assert result.gap_metrics.f1 == 1.0
    assert result.manual_review_items
    assert {item.status for item in result.manual_review_items} == {"pending"}


def test_evaluator_reports_hallucinated_missing_duplicate_and_ungrounded_tasks() -> None:
    result = evaluate_research_plan(
        _case("C01"),
        _plan(
            tasks=[
                _task(1, "road", "planned"),
                _task(2, "road", "planned"),
                _task(3, "poi", "planned", source="source.hallucinated"),
            ]
        ),
        allowed_strings={"source.ok"},
    )

    assert result.forbidden_task_count == 1
    assert result.missing_task_kinds == ["building"]
    assert result.duplicate_task_kinds == ["road"]
    assert result.ungrounded_refs == ["source.hallucinated"]
    assert result.grounding_pass is False


def test_evaluator_reports_wrong_gap_precedence_order_and_delivery_state() -> None:
    result = evaluate_research_plan(
        _case("C01"),
        _plan(tasks=[_task(2, "building", "pending"), _task(2, "road", "gap")]),
        allowed_strings={"source.ok"},
    )

    assert result.gap_metrics.f1 == 0.0
    assert result.precedence_pass is False
    assert result.order_valid is False
    assert result.delivery_state_pass is False


def test_negative_control_reject_with_no_tasks_is_fully_automatic() -> None:
    result = evaluate_research_plan(
        _case("C03"),
        _plan(decision="reject"),
        allowed_strings=set(),
    )

    assert result.automatic_score == 1.0
    assert result.task_metrics.f1 == 1.0
    assert result.gap_metrics.f1 == 1.0
    assert result.manual_review_items == []


def test_provider_or_schema_failure_remains_invalid_without_fallback() -> None:
    result = evaluate_research_plan(
        _case("C06"),
        None,
        allowed_strings=set(),
        failure_class="schema_validation_error",
    )

    assert result.pre_fallback_valid is False
    assert result.decision_valid is False
    assert result.automatic_score < 1.0
    assert result.failure_class == "schema_validation_error"
