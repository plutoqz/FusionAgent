from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from benchmark_platform.canonical import canonical_sha256
from benchmark_platform.models import BenchmarkPlatformValidationError, FailureClass, FailureRecord


class OracleError(BenchmarkPlatformValidationError):
    """Raised when a template oracle is not closed or cannot be solved."""


class TaskPlanSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    required: bool
    legal_source_ids: tuple[str, ...]
    allowed_delivery_states: tuple[str, ...]
    valid_combinations: tuple[dict[str, Any], ...] = Field(min_length=1)
    must: tuple[str, ...]
    forbidden: tuple[str, ...]


class OracleProof(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    solver_id: str
    template_family_id: str
    allowed_decisions: tuple[str, ...]
    task_plans: tuple[TaskPlanSet, ...]
    veto_ids: tuple[str, ...]
    proof_hash: str


def _fail(code: str, message: str, path: tuple[str | int, ...] = ()) -> None:
    raise OracleError([
        FailureRecord(
            failure_class=FailureClass.RUNTIME_INVALID_STATE,
            message=message,
            path=path,
            validator="oracle",
            details={"code": code},
        )
    ])


def _latest_delivery(task: Mapping[str, Any]) -> str:
    history = task.get("delivery_history", [])
    if not history:
        return "planned"
    ordered = sorted((item for item in history if isinstance(item, Mapping)), key=lambda item: int(item.get("step", 0)))
    return str(ordered[-1].get("state", "planned")) if ordered else "planned"


def _legal_sources(task: Mapping[str, Any], constraint: Mapping[str, Any]) -> tuple[str, ...]:
    allowed = set(str(item) for item in constraint.get("allowed_source_ids", []))
    forbidden = set(str(item) for item in constraint.get("forbidden_source_ids", []))
    legal: list[str] = []
    for source in task.get("source_states", []):
        if not isinstance(source, Mapping):
            continue
        source_id = str(source.get("source_id", ""))
        if not source_id or (allowed and source_id not in allowed) or source_id in forbidden:
            continue
        if source.get("legal_for_task") is not True:
            continue
        if source.get("availability") not in {"available", "delayed"}:
            continue
        if source.get("semantic_status") not in {"compatible", "requires_normalization"}:
            continue
        legal.append(source_id)
    return tuple(sorted(set(legal)))


def solve_template_oracle(template: Mapping[str, Any]) -> OracleProof:
    oracle = template.get("oracle")
    tasks = template.get("task_state", {}).get("tasks", [])
    if not isinstance(oracle, Mapping) or not isinstance(tasks, list) or not tasks:
        _fail("missing_oracle", "template oracle and non-empty tasks are required")
    allowed_decisions = tuple(str(item) for item in oracle.get("allowed_decisions", []))
    if not allowed_decisions:
        _fail("empty_decisions", "oracle allowed_decisions must be non-empty")
    constraints = {str(item.get("task_id")): item for item in oracle.get("task_constraints", []) if isinstance(item, Mapping)}
    task_plans: list[TaskPlanSet] = []
    for index, task in enumerate(tasks):
        if not isinstance(task, Mapping) or not task.get("task_id"):
            _fail("invalid_task", "oracle task must contain task_id", ("task_state", "tasks", index))
        task_id = str(task["task_id"])
        constraint = constraints.get(task_id)
        if constraint is None:
            _fail("missing_constraint", f"oracle has no constraint for task: {task_id}")
        states = tuple(str(item) for item in constraint.get("allowed_delivery_states", []))
        if not states:
            _fail("empty_delivery_states", f"task has no allowed delivery states: {task_id}")
        current = _latest_delivery(task)
        legal_sources = _legal_sources(task, constraint)
        if current not in states:
            _fail("delivery_state_unsatisfied", f"current delivery state is outside oracle: {task_id}")
        if constraint.get("required") is True and not task.get("source_states") and "planned" not in states:
            _fail("required_task_unsolved", f"required task has no source state or planned allowance: {task_id}")
        source_choices = legal_sources or (None,)
        combinations = tuple(
            {"decision": decision, "delivery_state": state, "source_id": source}
            for decision in allowed_decisions
            for state in states
            for source in source_choices
            if source is not None or state in {"planned", "pending", "gap", "rejected"}
        )
        if not combinations:
            _fail("no_legal_plan", f"oracle produced no legal combination: {task_id}")
        must = ("task_present",) if constraint.get("required") is True else ()
        forbidden = tuple(f"source:{item}" for item in constraint.get("forbidden_source_ids", []))
        task_plans.append(TaskPlanSet(task_id=task_id, required=bool(constraint.get("required")), legal_source_ids=legal_sources, allowed_delivery_states=states, valid_combinations=combinations, must=must, forbidden=forbidden))
    proof_payload = {
        "solver_id": "finite-state-task-contract.v1",
        "template_family_id": template.get("template_family_id"),
        "allowed_decisions": list(allowed_decisions),
        "task_plans": [item.model_dump(mode="json") for item in task_plans],
        "veto_ids": [str(item.get("veto_id")) for item in template.get("vetoes", []) if isinstance(item, Mapping)],
    }
    return OracleProof(**proof_payload, proof_hash=canonical_sha256(proof_payload))
