from __future__ import annotations

import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL_PHASES = {"succeeded", "failed", "cancelled"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_control(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def mark_timed_out(control: dict[str, Any], *, elapsed_seconds: float) -> None:
    timeout_seconds = float(control.get("timeout_seconds") or 0.0)
    source_id = str(control.get("source_id") or "")
    message = (
        "SOURCE_DOWNLOAD_FAILED: input acquisition timed out "
        f"after {timeout_seconds:g}s for source_id={source_id}"
    )
    write_acquisition_event(
        control,
        kind="source_acquisition_failed",
        phase="failed",
        progress=100,
        message="Source acquisition timed out during task-driven input materialization.",
        details={
            **_base_details(control),
            "elapsed_seconds": round(float(elapsed_seconds), 3),
            "error": f"TimeoutError: {message}",
            "fault_class": "SOURCE_DOWNLOAD_FAILED",
            "will_try_next_candidate": False,
            "watchdog": "process",
        },
        terminal_error=message,
    )
    marker_path = Path(str(control["marker_path"]))
    marker_path.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write_json(
        marker_path,
        {
            "status": "timed_out",
            "source_id": source_id,
            "elapsed_seconds": round(float(elapsed_seconds), 3),
            "timeout_seconds": timeout_seconds,
            "error": message,
            "updated_at": utc_now(),
        },
    )


def write_heartbeat(control: dict[str, Any], *, elapsed_seconds: float) -> None:
    write_acquisition_event(
        control,
        kind="source_acquisition_heartbeat",
        phase="running",
        progress=39,
        message="Source acquisition is still running.",
        details={
            **_base_details(control),
            "elapsed_seconds": round(float(elapsed_seconds), 3),
            "timeout_seconds": float(control.get("timeout_seconds") or 0.0),
            "watchdog": "process",
        },
    )


def write_acquisition_event(
    control: dict[str, Any],
    *,
    kind: str,
    phase: str,
    progress: int,
    message: str,
    details: dict[str, Any],
    terminal_error: str | None = None,
) -> None:
    status_path = Path(str(control["status_path"]))
    audit_path = Path(str(control["audit_path"]))
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        status = {
            "run_id": control.get("run_id"),
            "phase": phase,
            "progress": progress,
            "event_count": 0,
            "checkpoint": {},
        }
    if str(status.get("phase") or "") in TERMINAL_PHASES:
        return

    timestamp = utc_now()
    plan_revision = int(control.get("plan_revision") or status.get("plan_revision") or 0)
    event = {
        "timestamp": timestamp,
        "kind": kind,
        "phase": phase,
        "message": message,
        "plan_revision": plan_revision,
        "progress": progress,
        "attempt_no": int(status.get("attempt_no") or 0),
        "current_step": status.get("current_step"),
        "details": details,
    }

    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False))
        handle.write("\n")

    status["phase"] = phase
    status["progress"] = progress
    status["updated_at"] = timestamp
    status["plan_revision"] = plan_revision
    status["audit_path"] = str(audit_path)
    status["event_count"] = int(status.get("event_count") or 0) + 1
    status["last_event"] = event
    status["checkpoint"] = {
        "stage": "input_resolution",
        "plan_revision": plan_revision,
    }
    if terminal_error:
        status["error"] = terminal_error
        status["failure_summary"] = (
            f"{terminal_error} | failure_category=SOURCE_DOWNLOAD_FAILED | suggested_action=replan"
        )
        status["finished_at"] = timestamp
    _atomic_write_json(status_path, status)


def run_watchdog(control_path: Path) -> int:
    control = load_control(control_path)
    heartbeat_seconds = max(0.1, float(control.get("heartbeat_seconds") or 30.0))
    timeout_seconds = max(0.1, float(control.get("timeout_seconds") or 600.0))
    stop_path = Path(str(control["stop_path"]))
    marker_path = Path(str(control["marker_path"]))
    started = time.monotonic()
    next_heartbeat = started + heartbeat_seconds

    while True:
        if stop_path.exists():
            return 0
        if marker_path.exists():
            return 0
        elapsed = time.monotonic() - started
        if elapsed >= timeout_seconds:
            mark_timed_out(control, elapsed_seconds=elapsed)
            return 2
        now = time.monotonic()
        if now >= next_heartbeat:
            write_heartbeat(control, elapsed_seconds=elapsed)
            next_heartbeat = now + heartbeat_seconds
        time.sleep(min(0.2, max(0.05, next_heartbeat - time.monotonic())))


def _base_details(control: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": str(control.get("source_id") or ""),
        "candidate_index": int(control.get("candidate_index") or 1),
        "candidate_count": int(control.get("candidate_count") or 1),
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: source_acquisition_watchdog.py CONTROL_PATH", file=sys.stderr)
        return 64
    return run_watchdog(Path(argv[1]))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
