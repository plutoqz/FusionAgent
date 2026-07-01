from __future__ import annotations

from schemas.scenario_failure import ScenarioChildFailureRecord


class ScenarioFailureHandlerService:
    def build_child_failure_record(
        self,
        *,
        scenario_id: str,
        child_result: dict[str, object],
        recovery_hint: dict[str, object],
    ) -> ScenarioChildFailureRecord:
        recoverable = bool(recovery_hint.get("recoverable"))
        action = str(recovery_hint.get("recovery_action") or "")
        operator_action = str(recovery_hint.get("operator_action") or "")
        if recoverable and action not in {"", "none"}:
            state = "retry_scheduled"
            next_action = action
        elif operator_action:
            state = "blocked"
            next_action = operator_action
        else:
            state = "exhausted"
            next_action = "manual_review"
        return ScenarioChildFailureRecord(
            scenario_id=scenario_id,
            run_id=child_result.get("run_id"),
            job_type=str(child_result.get("job_type") or ""),
            task_kind=str(child_result.get("task_kind") or child_result.get("job_type") or ""),
            task_family=str(child_result.get("task_family") or child_result.get("job_type") or ""),
            error=str(child_result.get("error") or ""),
            error_code=str(child_result.get("failure_code") or _classify_child_error(child_result.get("error")) or ""),
            recoverable=recoverable,
            recovery_state=state,
            next_action=str(child_result.get("next_action") or next_action),
            retry_after_seconds=_retry_after_seconds(child_result),
            attempted_sources=_attempted_sources(child_result),
        )


def _retry_after_seconds(child_result: dict[str, object]) -> int | None:
    for event in child_result.get("audit_events") or []:
        details = getattr(event, "details", {})
        attempts = details.get("provider_attempts", []) if isinstance(details, dict) else []
        for attempt in attempts:
            if isinstance(attempt, dict) and attempt.get("next_retry_after_seconds") is not None:
                return int(attempt["next_retry_after_seconds"])
    return None


def _attempted_sources(child_result: dict[str, object]) -> list[dict[str, object]]:
    attempts = []
    for event in child_result.get("audit_events") or []:
        details = getattr(event, "details", {})
        if isinstance(details, dict):
            attempts.extend(item for item in details.get("provider_attempts", []) if isinstance(item, dict))
    return attempts


def _classify_child_error(error: object) -> str:
    text = str(error or "").casefold()
    if "child_run_timeout" in text:
        return "CHILD_RUN_TIMEOUT"
    if "aoi_resolution_required" in text:
        return "AOI_RESOLUTION_REQUIRED"
    if "aoi_resolution_failed" in text or "no aoi candidates" in text:
        return "AOI_RESOLUTION_FAILED"
    if "geocoder" in text and "timeout" in text:
        return "GEOCODER_TIMEOUT"
    if "source_download_failed" in text and "timeout" in text:
        return "SOURCE_FETCH_TIMEOUT"
    if "missing" in text and "source" in text:
        return "MISSING_REQUIRED_SOURCE"
    return "ALGO_RUNTIME_ERROR" if text else ""
