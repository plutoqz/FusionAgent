from __future__ import annotations

import json
import math
from typing import Any


def estimate_json_size_bytes(payload: object) -> int:
    return len(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))


def normalize_llm_usage(raw: object) -> dict[str, int | None]:
    usage = raw if isinstance(raw, dict) else {}
    return {
        "prompt_tokens": _optional_non_negative_int(usage.get("prompt_tokens")),
        "completion_tokens": _optional_non_negative_int(usage.get("completion_tokens")),
        "total_tokens": _optional_non_negative_int(usage.get("total_tokens")),
    }


def _optional_non_negative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        if math.isfinite(value) and value.is_integer() and value >= 0:
            return int(value)
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdigit():
            return int(stripped)
    return None


def build_run_telemetry_summary(
    *,
    status: object,
    audit_events: list[object],
    plan: object | None,
) -> dict[str, Any]:
    plan_context = getattr(plan, "context", {}) if plan is not None else {}
    if not isinstance(plan_context, dict):
        plan_context = {}

    status_planning = getattr(status, "planning_telemetry", {}) or {}
    planning = status_planning if isinstance(status_planning, dict) else {}
    if not planning:
        raw_plan_telemetry = plan_context.get("planning_telemetry", {})
        planning = raw_plan_telemetry if isinstance(raw_plan_telemetry, dict) else {}

    event_counts: dict[str, int] = {}
    last_event_kind: str | None = None
    last_event_at: str | None = None
    for event in audit_events:
        kind = str(getattr(event, "kind", "") or "").strip()
        if not kind:
            continue
        event_counts[kind] = event_counts.get(kind, 0) + 1
        last_event_kind = kind
        last_event_at = str(getattr(event, "timestamp", "") or "") or None

    return {
        "planning": dict(planning),
        "audit_event_count": len(audit_events),
        "event_counts": event_counts,
        "last_event_kind": last_event_kind,
        "last_event_at": last_event_at,
        "plan_revision": getattr(status, "plan_revision", 0),
        "attempt_no": getattr(status, "attempt_no", 0),
        "current_step": getattr(status, "current_step", None),
    }
