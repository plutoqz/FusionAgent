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
    policy_id: str | None = None
    soft_failure_reasons: list[str] = Field(default_factory=list)
    degraded_mode: bool = False
    degradation_level: str | None = None
    degradation_reason: str | None = None
    degradation_context: dict[str, Any] = Field(default_factory=dict)
    policy_adaptations: list[dict[str, Any]] = Field(default_factory=list)
    raw_quality_passed: bool | None = None
    adapted_quality_passed: bool | None = None
