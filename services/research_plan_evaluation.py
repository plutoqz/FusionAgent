from __future__ import annotations

from collections import Counter
from typing import Any, Iterable, Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas.research_case_manifest import ResearchCase
from schemas.research_llm_pilot import ResearchPlanningDecision


EVALUATOR_ID = "fusionagent.research-plan-evaluator.v1"


class SetMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    true_positive: int
    predicted_count: int
    expected_count: int
    precision: float
    recall: float
    f1: float


class AutomaticCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: str
    passed: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ManualReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    status: Literal["pending"] = "pending"


class ResearchPlanEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluator_id: str = EVALUATOR_ID
    case_id: str
    pre_fallback_valid: bool
    failure_class: str | None = None
    decision_valid: bool
    grounding_pass: bool
    ungrounded_refs: list[str] = Field(default_factory=list)
    task_metrics: SetMetrics
    forbidden_task_count: int
    forbidden_task_rate: float
    missing_task_kinds: list[str] = Field(default_factory=list)
    duplicate_task_kinds: list[str] = Field(default_factory=list)
    gap_metrics: SetMetrics
    precedence_pass: bool
    order_valid: bool
    delivery_state_pass: bool
    automatic_checks: list[AutomaticCheck]
    automatic_score: float
    manual_review_items: list[ManualReviewItem] = Field(default_factory=list)


def evaluate_research_plan(
    case: ResearchCase,
    plan: ResearchPlanningDecision | None,
    *,
    allowed_strings: Iterable[str],
    failure_class: str | None = None,
) -> ResearchPlanEvaluation:
    """Evaluate only claims that are mechanically observable in the planning JSON."""
    rubric = case.gold_rubric
    allowed = {str(value) for value in allowed_strings}
    tasks = list(plan.tasks) if plan is not None else []
    task_kinds = [task.task_kind for task in tasks]
    expected_tasks = set(rubric.expected_task_kinds)
    predicted_tasks = set(task_kinds)
    forbidden_tasks = sorted(predicted_tasks - expected_tasks)
    missing_tasks = sorted(expected_tasks - predicted_tasks)
    duplicates = sorted(kind for kind, count in Counter(task_kinds).items() if count > 1)

    predicted_gaps = {task.task_kind for task in tasks if task.delivery_state == "gap"}
    expected_gaps = set(rubric.expected_gap_task_kinds)
    task_metrics = _set_metrics(predicted_tasks, expected_tasks)
    gap_metrics = _set_metrics(predicted_gaps, expected_gaps)

    refs = {
        ref
        for task in tasks
        for ref in [*task.source_ids, *([task.algorithm_id] if task.algorithm_id else [])]
    }
    ungrounded_refs = sorted(refs - allowed)
    pre_fallback_valid = plan is not None and failure_class is None
    decision_valid = pre_fallback_valid and plan.decision in rubric.allowed_decisions

    orders = [task.order for task in tasks]
    order_valid = len(orders) == len(set(orders)) and sorted(orders) == list(range(1, len(orders) + 1))
    first_order: dict[str, int] = {}
    for task in tasks:
        first_order.setdefault(task.task_kind, task.order)
    precedence_failures = [
        [before, after]
        for before, after in rubric.required_precedence
        if before not in first_order or after not in first_order or first_order[before] >= first_order[after]
    ]
    precedence_pass = pre_fallback_valid and not precedence_failures

    delivery_violations = [
        {
            "task_kind": task.task_kind,
            "actual": task.delivery_state,
            "allowed": rubric.allowed_delivery_states.get(task.task_kind, []),
        }
        for task in tasks
        if task.task_kind not in rubric.allowed_delivery_states
        or task.delivery_state not in rubric.allowed_delivery_states[task.task_kind]
    ]
    delivery_state_pass = pre_fallback_valid and not delivery_violations
    grounding_pass = pre_fallback_valid and not ungrounded_refs

    checks = [
        AutomaticCheck(
            check_id="pre_fallback_valid",
            passed=pre_fallback_valid,
            details={"failure_class": failure_class},
        ),
        AutomaticCheck(check_id="decision_allowed", passed=decision_valid),
        AutomaticCheck(
            check_id="references_grounded",
            passed=grounding_pass,
            details={"ungrounded_refs": ungrounded_refs},
        ),
        AutomaticCheck(
            check_id="task_set_exact",
            passed=pre_fallback_valid and not forbidden_tasks and not missing_tasks and not duplicates,
            details={
                "forbidden": forbidden_tasks,
                "missing": missing_tasks,
                "duplicates": duplicates,
            },
        ),
        AutomaticCheck(
            check_id="gap_set_exact",
            passed=pre_fallback_valid and predicted_gaps == expected_gaps,
            details={
                "predicted": sorted(predicted_gaps),
                "expected": sorted(expected_gaps),
            },
        ),
        AutomaticCheck(
            check_id="task_order_valid",
            passed=pre_fallback_valid and order_valid,
            details={"orders": orders},
        ),
        AutomaticCheck(
            check_id="required_precedence",
            passed=precedence_pass,
            details={"failures": precedence_failures},
        ),
        AutomaticCheck(
            check_id="delivery_states_allowed",
            passed=delivery_state_pass,
            details={"violations": delivery_violations},
        ),
    ]
    automatic_score = sum(check.passed for check in checks) / len(checks)
    forbidden_rate = len(forbidden_tasks) / len(predicted_tasks) if predicted_tasks else 0.0
    return ResearchPlanEvaluation(
        case_id=case.case_id,
        pre_fallback_valid=pre_fallback_valid,
        failure_class=failure_class,
        decision_valid=decision_valid,
        grounding_pass=grounding_pass,
        ungrounded_refs=ungrounded_refs,
        task_metrics=task_metrics,
        forbidden_task_count=len(forbidden_tasks),
        forbidden_task_rate=forbidden_rate,
        missing_task_kinds=missing_tasks,
        duplicate_task_kinds=duplicates,
        gap_metrics=gap_metrics,
        precedence_pass=precedence_pass,
        order_valid=pre_fallback_valid and order_valid,
        delivery_state_pass=delivery_state_pass,
        automatic_checks=checks,
        automatic_score=automatic_score,
        manual_review_items=[ManualReviewItem(item_id=item) for item in rubric.manual_review_items],
    )


def _set_metrics(predicted: set[str], expected: set[str]) -> SetMetrics:
    true_positive = len(predicted & expected)
    precision = true_positive / len(predicted) if predicted else (1.0 if not expected else 0.0)
    recall = true_positive / len(expected) if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return SetMetrics(
        true_positive=true_positive,
        predicted_count=len(predicted),
        expected_count=len(expected),
        precision=precision,
        recall=recall,
        f1=f1,
    )
