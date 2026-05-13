from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


FAILURE_CATEGORIES = [
    "SOURCE_MISSING",
    "SOURCE_CORRUPTED",
    "CRS_MISMATCH",
    "PARAM_OUT_OF_RANGE",
    "ALGO_RUNTIME_ERROR",
    "ALGO_TIMEOUT",
    "SUSPECT_OUTPUT",
]


class FailureDetails(BaseModel):
    failure_category: str
    root_cause: str
    recoverable: bool
    suggested_action: str


def classify_failure_category(raw: str | None) -> str:
    text = str(raw or "").strip().lower()
    if not text:
        return "ALGO_RUNTIME_ERROR"
    if "source_missing" in text or "missing source" in text or "source missing" in text or "fault=source_missing" in text:
        return "SOURCE_MISSING"
    if (
        "source_corrupted" in text
        or "corrupted shapefile" in text
        or "source corrupted" in text
        or "fault=source_corrupted" in text
    ):
        return "SOURCE_CORRUPTED"
    if "crs_mismatch" in text or "crs mismatch" in text or "fault=crs_mismatch" in text:
        return "CRS_MISMATCH"
    if "param_out_of_range" in text or "out of range" in text:
        return "PARAM_OUT_OF_RANGE"
    if "algo_timeout" in text or "timeout" in text or "timed out" in text:
        return "ALGO_TIMEOUT"
    if "suspect_output" in text or "suspect output" in text or "semantically empty" in text:
        return "SUSPECT_OUTPUT"
    return "ALGO_RUNTIME_ERROR"


def classify_failure_details(
    *,
    error: str | None = None,
    reason_code: str | None = None,
    recoverable: Optional[bool] = None,
    suggested_action: Optional[str] = None,
) -> FailureDetails:
    root_cause = str(reason_code or "unknown_reason").strip().upper()
    if not root_cause:
        root_cause = "UNKNOWN_REASON"
    category = classify_failure_category(reason_code or error)
    resolved_recoverable = True if recoverable is None else bool(recoverable)
    resolved_action = str(suggested_action or ("replan" if resolved_recoverable else "inspect_and_retry")).strip()
    if not resolved_action:
        resolved_action = "replan" if resolved_recoverable else "inspect_and_retry"
    return FailureDetails(
        failure_category=category,
        root_cause=root_cause,
        recoverable=resolved_recoverable,
        suggested_action=resolved_action,
    )
