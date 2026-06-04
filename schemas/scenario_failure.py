from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ScenarioChildFailureRecord(BaseModel):
    scenario_id: str
    run_id: str | None = None
    job_type: str
    task_kind: str
    task_family: str
    error: str | None = None
    recoverable: bool = False
    recovery_state: str
    next_action: str
    retry_after_seconds: int | None = None
    attempted_sources: list[dict[str, Any]] = Field(default_factory=list)
