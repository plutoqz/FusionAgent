from __future__ import annotations

from pydantic import BaseModel


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
