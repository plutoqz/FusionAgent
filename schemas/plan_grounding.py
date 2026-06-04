from __future__ import annotations

from pydantic import BaseModel, Field


class PlanGroundingGateDecision(BaseModel):
    mode: str
    allowed: bool
    reason_code: str | None = None
    message: str = ""
    grounding_score: float | None = None
    issue_codes: list[str] = Field(default_factory=list)
