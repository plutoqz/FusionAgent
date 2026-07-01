from __future__ import annotations

from pydantic import BaseModel, Field


class SourceAcquisitionAttempt(BaseModel):
    source_id: str
    status: str
    attempt_type: str = "provider"
    attempt_no: int = 1
    channel: str | None = None
    fault_class: str | None = None
    fault_message: str | None = None
    recoverable: bool = False
    next_retry_after_seconds: int | None = None
    coverage_status: str | None = None
    feature_count: int | None = None
    selected_for_fusion: bool = False
    external_uncontrollable: bool = False
    skill_id: str | None = None
    skill_name: str | None = None
    capability: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class SourceAcquisitionJob(BaseModel):
    job_id: str
    scenario_id: str | None = None
    run_id: str | None = None
    source_id: str
    status: str
    attempt: int = 0
    next_retry_at: str | None = None
    retry_window_expires_at: str | None = None
    fault_class: str | None = None
    fault_message: str | None = None
    missing_config: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
