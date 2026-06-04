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
            recoverable=recoverable,
            recovery_state=state,
            next_action=next_action,
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
