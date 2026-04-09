import math

import pytest
from pydantic import ValidationError

from schemas.agent import (
    ArtifactReuseDecision,
    DecisionCandidate,
    DecisionRecord,
    RunPhase,
    RunStatus,
    RunTrigger,
    RunTriggerType,
)
from schemas.fusion import JobType


def test_run_status_accepts_decision_and_reuse_states() -> None:
    trigger = RunTrigger(type=RunTriggerType.user_query, content="verify schema")
    candidate = DecisionCandidate(
        candidate_id="candidate-1",
        score=0.42,
        reason="heuristic",
        evidence={"metrics": {"success_rate": 0.42}, "meta": {"source": "test"}},
    )
    decision = DecisionRecord(
        decision_type="artifact_selection",
        selected_id=candidate.candidate_id,
        selected_score=candidate.score,
        rationale="preferred this option",
        candidates=[candidate],
    )
    reuse_decision = ArtifactReuseDecision(
        reused=True,
        artifact_id="artifact-abc",
        freshness_status="fresh",
        rationale="matches latest policy",
    )

    status = RunStatus(
        run_id="run-123",
        job_type=JobType.building,
        trigger=trigger,
        phase=RunPhase.running,
        target_crs="EPSG:4326",
        created_at="2026-04-07T00:00:00Z",
        decision_records=[decision],
        artifact_reuse=reuse_decision,
    )

    record = status.decision_records[0]
    assert len(status.decision_records) == 1
    assert record.selected_score == 0.42
    assert record.policy_version == "v2"
    assert record.evidence_refs == []
    assert record.candidates[0].evidence["meta"]["source"] == "test"
    assert status.artifact_reuse and status.artifact_reuse.reused

    round_trip = RunStatus.model_validate(status.model_dump())
    assert round_trip == status


def test_decision_validators_reject_inconsistencies() -> None:
    candidate = DecisionCandidate(candidate_id="candidate-1", score=0.5, reason="heuristic", evidence={})
    with pytest.raises(ValidationError):
        DecisionRecord(
            decision_type="artifact_selection",
            selected_id=candidate.candidate_id,
            selected_score=0.55,
            rationale="preferred this option",
            candidates=[candidate],
        )
def test_score_tolerance_allows_close_matches() -> None:
    candidate = DecisionCandidate(candidate_id="candidate-2", score=0.1 + 0.2, reason="float math", evidence={})
    record = DecisionRecord(
        decision_type="artifact_selection",
        selected_id=candidate.candidate_id,
        selected_score=0.3,
        rationale="float tolerant",
        candidates=[candidate],
    )
    assert math.isclose(record.candidates[0].score, 0.3, rel_tol=1e-9, abs_tol=1e-9)
    with pytest.raises(ValidationError):
        ArtifactReuseDecision(
            reused=True,
            freshness_status="unknown",
            rationale="missing artifact id",
        )
