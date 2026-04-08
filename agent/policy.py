from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from pydantic import BaseModel, Field, model_validator

from schemas.agent import DecisionCandidate, DecisionRecord


class CandidateScoreInput(BaseModel):
    """
    Normalized candidate metrics for deterministic policy selection.

    All scalar scores are expected to be in [0.0, 1.0] where higher is better.
    Optional fields may be omitted; missing values are treated as neutral (0.5)
    for optional metrics. For core metrics, missing values are treated as 0.0 so
    that omitting a primary metric never inflates a candidate.
    """

    candidate_id: str

    # Core: strongest influence (either may be provided; both allowed).
    success_rate: Optional[float] = None
    accuracy: Optional[float] = None

    # Core: second tier influence.
    data_quality: Optional[float] = None
    stability: Optional[float] = None

    # Core: third tier influence.
    freshness: Optional[float] = None
    reuse: Optional[float] = None

    # Optional: supported but not required by tests.
    speed: Optional[float] = None
    cost: Optional[float] = None

    # Free-form, not used by scoring; useful for callers.
    meta: Dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_ranges(self) -> "CandidateScoreInput":
        for name in (
            "success_rate",
            "accuracy",
            "data_quality",
            "stability",
            "freshness",
            "reuse",
            "speed",
            "cost",
        ):
            value = getattr(self, name)
            if value is None:
                continue
            if not (0.0 <= float(value) <= 1.0):
                raise ValueError(f"{name} must be in [0.0, 1.0] when provided.")
        return self


@dataclass(frozen=True)
class _Weights:
    # Priority order (largest to smallest): success/accuracy, quality/stability,
    # freshness/reuse, then speed/cost.
    success_accuracy: float = 0.58
    data_quality: float = 0.20
    stability: float = 0.12
    freshness: float = 0.05
    reuse: float = 0.03
    speed: float = 0.01
    cost: float = 0.01


class PolicyEngine:
    """
    Small deterministic policy engine.

    Selection is a fixed weighted sum aligned with current priority:
    success_rate/accuracy strongest, then data_quality/stability, then freshness/reuse,
    then speed/cost as low-priority tie shapers.
    """

    def __init__(self, policy_version: str = "v2", weights: Optional[_Weights] = None) -> None:
        self.policy_version = policy_version
        self._w = weights or _Weights()

    def select(self, decision_type: str, candidates: List[CandidateScoreInput]) -> DecisionRecord:
        if not candidates:
            raise ValueError("candidates must be non-empty.")

        scored: List[Tuple[CandidateScoreInput, float, str]] = []
        for c in candidates:
            score, reason = self._score_one(c)
            scored.append((c, score, reason))

        # Deterministic: highest score wins; ties broken by candidate_id asc.
        scored_sorted = sorted(scored, key=lambda t: (-t[1], t[0].candidate_id))
        winner, winner_score, _ = scored_sorted[0]

        decision_candidates = [
            DecisionCandidate(candidate_id=c.candidate_id, score=s, reason=r)
            for (c, s, r) in scored_sorted
        ]

        rationale = self._build_rationale(winner, winner_score, scored_sorted)

        return DecisionRecord(
            decision_type=decision_type,
            selected_id=winner.candidate_id,
            selected_score=winner_score,
            rationale=rationale,
            candidates=decision_candidates,
            policy_version=self.policy_version,
        )

    def _score_one(self, c: CandidateScoreInput) -> Tuple[float, str]:
        primary = self._primary_success_accuracy(c)
        dq = self._core_or_zero(c.data_quality)
        st = self._core_or_zero(c.stability)
        fr = self._neutral_if_missing(c.freshness)
        re = self._neutral_if_missing(c.reuse)
        sp = self._neutral_if_missing(c.speed)
        co = self._neutral_if_missing(c.cost)

        score = (
            self._w.success_accuracy * primary
            + self._w.data_quality * dq
            + self._w.stability * st
            + self._w.freshness * fr
            + self._w.reuse * re
            + self._w.speed * sp
            + self._w.cost * co
        )

        # Keep per-candidate explanation compact and deterministic.
        reason = (
            f"weighted_sum="
            f"{self._w.success_accuracy:.2f}*(success/accuracy={primary:.3f}) + "
            f"{self._w.data_quality:.2f}*(data_quality={dq:.3f}) + "
            f"{self._w.stability:.2f}*(stability={st:.3f}) + "
            f"{self._w.freshness:.2f}*(freshness={fr:.3f}) + "
            f"{self._w.reuse:.2f}*(reuse={re:.3f}) + "
            f"{self._w.speed:.2f}*(speed={sp:.3f}) + "
            f"{self._w.cost:.2f}*(cost={co:.3f})"
        )
        return (float(score), reason)

    @staticmethod
    def _core_or_zero(value: Optional[float]) -> float:
        return float(value) if value is not None else 0.0

    @staticmethod
    def _neutral_if_missing(value: Optional[float]) -> float:
        return float(value) if value is not None else 0.5

    @staticmethod
    def _primary_success_accuracy(c: CandidateScoreInput) -> float:
        # Missing primary metrics are treated as 0.0 to avoid "rewarding" omission.
        sr = 0.0 if c.success_rate is None else float(c.success_rate)
        acc = 0.0 if c.accuracy is None else float(c.accuracy)
        # Bias towards success_rate, still reflect accuracy.
        return 0.65 * sr + 0.35 * acc

    def _build_rationale(
        self,
        winner: CandidateScoreInput,
        winner_score: float,
        scored_sorted: List[Tuple[CandidateScoreInput, float, str]],
    ) -> str:
        # Mention major factors explicitly (testable, explainable).
        parts: List[str] = []
        parts.append(
            f"Selected '{winner.candidate_id}' with score={winner_score:.6f} "
            f"using deterministic weighted scoring."
        )
        parts.append(
            "Major factors: success_rate/accuracy (strongest), data_quality and stability, "
            "then freshness and reuse, then speed and cost."
        )

        # If optional fields are present, mention they are used only as low-priority factors.
        any_speed = any(c.speed is not None for (c, _, _) in scored_sorted)
        any_cost = any(c.cost is not None for (c, _, _) in scored_sorted)
        if any_speed or any_cost:
            extras = []
            if any_speed:
                extras.append("speed")
            if any_cost:
                extras.append("cost")
            parts.append(
                f"Optional fields present ({', '.join(extras)}); "
                f"used only with low weights (speed={self._w.speed:.2f}, cost={self._w.cost:.2f})."
            )

        # Contrast top-2 if available to make the rationale more useful but still short.
        if len(scored_sorted) >= 2:
            runner_up, runner_score, _ = scored_sorted[1]
            parts.append(
                f"Runner-up '{runner_up.candidate_id}' score={runner_score:.6f}; "
                f"winner had higher weighted sum on the major factors."
            )

        return " ".join(parts)
