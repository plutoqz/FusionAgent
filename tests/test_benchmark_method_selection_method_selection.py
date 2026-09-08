from __future__ import annotations

from benchmark_platform.selection import ConditionObservation, select_method


def _observation(condition_id: str, *, runs: int = 0, safe: bool = True, score: float = 0.5):
    return ConditionObservation(
        condition_id=condition_id,
        run_count=runs,
        safety_hard_gate_passed=safe,
        forbidden_action_rate=0.0,
        contract_vector=(score, score),
        human_blind_pass_rate=score,
        mechanism_rates={"causal": score, "invariance": score, "composition": score, "recovery": score},
        token_cost=100.0,
        latency_ms=10.0,
        repair_count=0,
        evidence_completeness=1.0,
    )


def test_selection_stays_closed_until_all_three_conditions_are_observed():
    result = select_method((_observation("llm_only"),))
    assert result.status == "not_selectable"
    assert result.selected_condition is None
    assert result.performance_scores_used is False


def test_complete_selection_uses_safety_then_contract_then_efficiency():
    result = select_method(
        (
            _observation("llm_only", runs=2, safe=True, score=0.7),
            _observation("llm_capability_kg", runs=2, safe=False, score=0.9),
            _observation("llm_full_contract_kg", runs=2, safe=True, score=0.8),
        )
    )
    assert result.status == "selected"
    assert result.selected_condition == "llm_full_contract_kg"
