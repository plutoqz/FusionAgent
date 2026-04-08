import pytest

from agent.policy import CandidateScoreInput, PolicyEngine


def test_policy_engine_selects_better_candidate_and_emits_rationale_and_candidates():
    engine = PolicyEngine()

    # Candidate B should win primarily due to stronger success_rate/accuracy,
    # with decent quality/stability. Freshness/reuse are lower-priority tie shapers.
    candidates = [
        CandidateScoreInput(
            candidate_id="A",
            success_rate=0.60,
            accuracy=0.60,
            data_quality=0.80,
            stability=0.80,
            freshness=0.20,
            reuse=0.20,
        ),
        CandidateScoreInput(
            candidate_id="B",
            success_rate=0.90,
            accuracy=0.90,
            data_quality=0.70,
            stability=0.70,
            freshness=0.20,
            reuse=0.20,
        ),
    ]

    record = engine.select("algorithm_selection", candidates)

    assert record.decision_type == "algorithm_selection"
    assert record.selected_id == "B"
    assert isinstance(record.selected_score, float)

    # Rationale must mention the major factors used.
    r = record.rationale.lower()
    assert "success_rate" in r or "success/accuracy" in r
    assert "data_quality" in r
    assert "stability" in r
    assert "freshness" in r
    assert "reuse" in r

    # Candidate list should include both, and selected candidate must match.
    assert len(record.candidates) == 2
    ids = [c.candidate_id for c in record.candidates]
    assert set(ids) == {"A", "B"}

    selected = next(c for c in record.candidates if c.candidate_id == record.selected_id)
    assert pytest.approx(selected.score, rel=0, abs=0) == record.selected_score
    assert "weighted_sum" in selected.reason


def test_policy_engine_missing_primary_metric_does_not_inflate_candidate():
    engine = PolicyEngine()

    # "MISSING_ACC" has success_rate=1.0 but omits accuracy; it should not beat
    # a candidate with strong values for both primary metrics.
    candidates = [
        CandidateScoreInput(
            candidate_id="FULL",
            success_rate=0.75,
            accuracy=0.75,
            data_quality=0.50,
            stability=0.50,
            freshness=0.50,
            reuse=0.50,
        ),
        CandidateScoreInput(
            candidate_id="MISSING_ACC",
            success_rate=1.00,
            accuracy=None,
            data_quality=0.50,
            stability=0.50,
            freshness=0.50,
            reuse=0.50,
        ),
    ]

    record = engine.select("algorithm_selection", candidates)
    assert record.selected_id == "FULL"


def test_policy_engine_speed_cost_are_low_priority_tie_shapers_and_accepted():
    engine = PolicyEngine()

    # Same major factors; speed/cost should decide.
    candidates = [
        CandidateScoreInput(
            candidate_id="SLOW_EXPENSIVE",
            success_rate=0.80,
            accuracy=0.80,
            data_quality=0.80,
            stability=0.80,
            freshness=0.80,
            reuse=0.80,
            speed=0.00,
            cost=0.00,
        ),
        CandidateScoreInput(
            candidate_id="FAST_CHEAP",
            success_rate=0.80,
            accuracy=0.80,
            data_quality=0.80,
            stability=0.80,
            freshness=0.80,
            reuse=0.80,
            speed=1.00,
            cost=1.00,
        ),
    ]

    record = engine.select("algorithm_selection", candidates)
    assert record.selected_id == "FAST_CHEAP"
    assert "speed" in record.rationale.lower()
    assert "cost" in record.rationale.lower()

    selected = next(c for c in record.candidates if c.candidate_id == record.selected_id)
    assert "speed" in selected.reason
    assert "cost" in selected.reason

    # But speed/cost should not dominate success/accuracy.
    candidates = [
        CandidateScoreInput(
            candidate_id="HIGH_SUCCESS_SLOW",
            success_rate=0.90,
            accuracy=0.90,
            data_quality=0.50,
            stability=0.50,
            freshness=0.50,
            reuse=0.50,
            speed=0.00,
            cost=0.00,
        ),
        CandidateScoreInput(
            candidate_id="LOW_SUCCESS_FAST",
            success_rate=0.85,
            accuracy=0.85,
            data_quality=0.50,
            stability=0.50,
            freshness=0.50,
            reuse=0.50,
            speed=1.00,
            cost=1.00,
        ),
    ]

    record = engine.select("algorithm_selection", candidates)
    assert record.selected_id == "HIGH_SUCCESS_SLOW"
