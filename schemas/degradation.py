from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class DegradationLevel(str, Enum):
    none = "none"
    partial_source = "partial_source"
    external_uncontrollable = "external_uncontrollable"
    system_failure = "system_failure"


class DegradationContext(BaseModel):
    degraded: bool = False
    level: DegradationLevel = DegradationLevel.none
    reason: str | None = None
    available_sources: list[str] = Field(default_factory=list)
    missing_sources: list[str] = Field(default_factory=list)
    external_uncontrollable_sources: list[str] = Field(default_factory=list)
    system_failure_sources: list[str] = Field(default_factory=list)

    @property
    def external_only(self) -> bool:
        return (
            self.degraded
            and self.level == DegradationLevel.external_uncontrollable
            and not self.system_failure_sources
        )
