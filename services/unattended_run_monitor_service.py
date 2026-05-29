from __future__ import annotations

from typing import Any


LONG_RUNNING_BOUNDARY = "process supervision and external scheduler uptime are environment responsibilities"


def classify_unattended_readiness(
    *,
    scheduled_errors: list[str],
    inbox_failed_count: int,
    recovery_enabled: bool,
    recovery_failed_count: int,
) -> str:
    if scheduled_errors or inbox_failed_count > 0 or recovery_failed_count > 0:
        return "degraded"
    if not recovery_enabled:
        return "degraded"
    return "ready"


def build_unattended_runtime_snapshot(
    *,
    scheduled_tick_result: dict[str, Any],
    inbox_result: dict[str, Any] | None,
    recovery_tick_result: dict[str, Any],
    recent_runs: list[dict[str, Any]],
) -> dict[str, Any]:
    spec_results = [item for item in scheduled_tick_result.get("spec_results", []) if isinstance(item, dict)]
    scheduled_errors = [str(item) for item in scheduled_tick_result.get("errors", [])]
    inbox_payload = inbox_result or {}
    inbox_failed = inbox_payload.get("failed", [])
    inbox_failed_count = len(inbox_failed) if isinstance(inbox_failed, list) else 0
    recovery_enabled = bool(recovery_tick_result.get("enabled", False))
    recovery_failed_count = int(recovery_tick_result.get("failed", 0) or 0)
    readiness = classify_unattended_readiness(
        scheduled_errors=scheduled_errors,
        inbox_failed_count=inbox_failed_count,
        recovery_enabled=recovery_enabled,
        recovery_failed_count=recovery_failed_count,
    )

    return {
        "readiness": readiness,
        "manual_intervention_required": readiness != "ready",
        "unattended_modes": {
            "scheduled": int(scheduled_tick_result.get("configured", 0) or 0) > 0,
            "scheduled_task_driven_auto": any(
                item.get("status") == "created" and item.get("input_strategy") == "task_driven_auto"
                for item in spec_results
            ),
            "local_inbox": bool(inbox_payload.get("processed")),
            "recovery_tick": recovery_enabled,
        },
        "scheduled_tick": scheduled_tick_result,
        "inbox": inbox_payload,
        "recovery_tick": recovery_tick_result,
        "recent_runs": recent_runs,
        "long_running_boundary": LONG_RUNNING_BOUNDARY,
    }
