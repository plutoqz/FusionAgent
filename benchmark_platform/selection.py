from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

from benchmark_platform.canonical import canonical_sha256
from benchmark_platform.context import CanonicalContext
from benchmark_platform.design_loader import FrozenDesignBundle
from benchmark_platform.models import BenchmarkPlatformValidationError, FailureClass, FailureRecord
from benchmark_platform.projections import project_condition


class SelectionError(BenchmarkPlatformValidationError):
    pass


class InterfaceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    interface_id: Literal["raw_full_kg", "task_conditioned_typed", "capped_query_on_demand"]
    complexity_rank: int = Field(ge=0)
    token_cap: int = Field(gt=0)
    information_fields: tuple[str, ...] = Field(min_length=1)


class InterfaceScreen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    interface_id: str
    closed: bool
    information_complete: bool
    estimated_tokens: int = Field(ge=0)
    complexity_rank: int = Field(ge=0)
    projection_hash: str | None = None
    failure_code: str | None = None


class InterfaceScreenReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    selection_contract_id: str
    context_semantic_hash: str
    candidate_screens: tuple[InterfaceScreen, ...] = Field(min_length=1)
    ordered_candidate_ids: tuple[str, ...] = Field(min_length=1)
    selection_hash: str
    performance_scores_used: bool = False


LLM_CONDITIONS = ("llm_only", "llm_capability_kg", "llm_full_contract_kg")


class ConditionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    condition_id: Literal["llm_only", "llm_capability_kg", "llm_full_contract_kg"]
    run_count: int = Field(ge=0)
    safety_hard_gate_passed: bool
    forbidden_action_rate: float = Field(ge=0, le=1)
    contract_vector: tuple[float, ...] = Field(min_length=1)
    human_blind_pass_rate: float = Field(ge=0, le=1)
    mechanism_rates: dict[str, float]
    token_cost: float = Field(ge=0)
    latency_ms: float = Field(ge=0)
    repair_count: int = Field(ge=0)
    evidence_completeness: float = Field(ge=0, le=1)


class MethodSelectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["not_selectable", "selected", "pareto_tie"]
    reason: str
    condition_order: tuple[str, ...]
    selected_condition: str | None = None
    observations_complete: bool
    performance_scores_used: bool = True
    selection_hash: str


def _fail(code: str, message: str) -> None:
    raise SelectionError([
        FailureRecord(
            failure_class=FailureClass.RUNTIME_INVALID_STATE,
            message=message,
            validator="interface_selection",
            details={"code": code},
        )
    ])


def screen_interface_candidates(
    bundle: FrozenDesignBundle,
    context: CanonicalContext,
    candidates: tuple[InterfaceCandidate, ...],
    *,
    request: Mapping[str, Any],
    output_schema: Mapping[str, Any],
    token_estimator: Mapping[str, int] | None = None,
) -> InterfaceScreenReport:
    if not candidates:
        _fail("empty_candidates", "at least one interface candidate is required")
    if len({item.interface_id for item in candidates}) != len(candidates):
        _fail("duplicate_candidate", "interface candidate IDs must be unique")
    estimates = token_estimator or {}
    screens: list[InterfaceScreen] = []
    for candidate in candidates:
        try:
            projection = project_condition(
                "llm_full_contract_kg",
                context,
                request=request,
                output_schema=output_schema,
                bundle=bundle,
            )
            payload = projection.payload["full_contract_projection"]
            missing = [field for field in candidate.information_fields if field not in payload]
            estimate = int(estimates.get(candidate.interface_id, len(str(payload)) // 4))
            closed = not missing and estimate <= candidate.token_cap
            screens.append(InterfaceScreen(
                interface_id=candidate.interface_id,
                closed=closed,
                information_complete=not missing,
                estimated_tokens=estimate,
                complexity_rank=candidate.complexity_rank,
                projection_hash=projection.spec.projection_hash if closed else None,
                failure_code=None if closed else ("information_incomplete" if missing else "token_cap_exceeded"),
            ))
        except SelectionError:
            raise
        except Exception as error:
            screens.append(InterfaceScreen(interface_id=candidate.interface_id, closed=False, information_complete=False, estimated_tokens=0, complexity_rank=candidate.complexity_rank, failure_code=type(error).__name__))
    valid = [item for item in screens if item.closed]
    if not valid:
        _fail("no_closed_candidate", "no full-contract interface candidate passed development screening")
    ordered = tuple(item.interface_id for item in sorted(valid, key=lambda item: (item.estimated_tokens, item.complexity_rank, item.interface_id)))
    selection_payload = {
        "selection_contract_id": "fusionagent.benchmark-platform.interface-screen.v1",
        "context_semantic_hash": context.semantic_hash,
        "candidate_screens": [item.model_dump(mode="json") for item in screens],
        "ordered_candidate_ids": list(ordered),
        "performance_scores_used": False,
    }
    return InterfaceScreenReport(**selection_payload, selection_hash=canonical_sha256(selection_payload))


def select_method(
    observations: tuple[ConditionObservation, ...],
    *,
    contract_margin: float = 0.0,
) -> MethodSelectionResult:
    """Apply the frozen lexicographic rule only after all three conditions are observed."""
    if not 0 <= contract_margin <= 1:
        _fail("invalid_margin", "contract margin must be within [0, 1]")
    by_id = {item.condition_id: item for item in observations}
    complete = set(by_id) == set(LLM_CONDITIONS) and all(by_id[item].run_count > 0 for item in LLM_CONDITIONS)
    if not complete:
        payload = {"status": "not_selectable", "reason": "all three LLM conditions require completed observations", "condition_order": list(LLM_CONDITIONS), "observations_complete": False, "performance_scores_used": False}
        return MethodSelectionResult(**payload, selection_hash=canonical_sha256(payload))
    unsafe = [item.condition_id for item in by_id.values() if not item.safety_hard_gate_passed]
    eligible = [item for item in by_id.values() if item.safety_hard_gate_passed]
    if not eligible:
        payload = {"status": "not_selectable", "reason": "no condition passes the safety hard gate", "condition_order": list(LLM_CONDITIONS), "observations_complete": True, "performance_scores_used": True}
        return MethodSelectionResult(**payload, selection_hash=canonical_sha256(payload))
    max_vector = max(item.contract_vector for item in eligible)
    top = [item for item in eligible if all(a + contract_margin >= b for a, b in zip(item.contract_vector, max_vector))]
    top.sort(key=lambda item: (item.token_cost, item.latency_ms, item.repair_count, -item.evidence_completeness, item.condition_id))
    selected = top[0]
    ties = [item for item in top if (item.token_cost, item.latency_ms, item.repair_count, -item.evidence_completeness) == (selected.token_cost, selected.latency_ms, selected.repair_count, -selected.evidence_completeness)]
    status = "pareto_tie" if len(ties) > 1 else "selected"
    payload = {"status": status, "reason": "lexicographic selection after safety and contract gates", "condition_order": [item.condition_id for item in top], "selected_condition": None if status == "pareto_tie" else selected.condition_id, "observations_complete": True, "performance_scores_used": True}
    return MethodSelectionResult(**payload, selection_hash=canonical_sha256(payload))
