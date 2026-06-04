from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from schemas.task_kind import TaskKind


class QualityGateReport(BaseModel):
    accepted: bool
    task_kind: TaskKind
    artifact_path: str
    checks: dict[str, dict[str, Any]] = Field(default_factory=dict)
    metrics: dict[str, Any] = Field(default_factory=dict)
    failure_reasons: list[str] = Field(default_factory=list)
