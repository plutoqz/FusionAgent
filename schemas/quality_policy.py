from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from schemas.task_kind import TaskKind


class QualityPolicyCheck(BaseModel):
    check_id: str
    metric_name: str
    severity: str = "hard"
    operator: str = "lte"
    threshold: float | int | bool | str | None = None
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class QualityPolicy(BaseModel):
    policy_id: str
    task_kind: TaskKind
    description: str = ""
    checks: list[QualityPolicyCheck] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
