from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TERMINAL_PHASES = {"succeeded", "failed"}


def collect_recoverable_runs(runs_root: Path, stale_after_seconds: int) -> list[dict[str, Any]]:
    root = Path(runs_root)
    if not root.exists():
        return []

    now = datetime.now(timezone.utc)
    stale_after = max(0, stale_after_seconds)
    records: list[tuple[datetime, dict[str, Any]]] = []
    for run_json_path in root.glob("*/run.json"):
        try:
            raw_record = json.loads(run_json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            continue
        if not isinstance(raw_record, dict):
            continue

        phase = str(raw_record.get("phase") or "").strip()
        if phase in TERMINAL_PHASES:
            continue

        updated_at = raw_record.get("updated_at")
        updated_at_text = updated_at if isinstance(updated_at, str) else None
        last_update = _parse_iso_datetime(updated_at_text)
        if last_update is None:
            try:
                last_update = datetime.fromtimestamp(run_json_path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue

        if (now - last_update).total_seconds() < stale_after:
            continue

        checkpoint = raw_record.get("checkpoint")
        checkpoint_payload = dict(checkpoint) if isinstance(checkpoint, dict) else {}
        record = {
            "run_id": str(raw_record.get("run_id") or run_json_path.parent.name),
            "phase": phase,
            "updated_at": updated_at_text or last_update.isoformat(),
            "checkpoint": checkpoint_payload,
            "recovery_action": classify_recovery_action(
                {
                    "phase": phase,
                    "checkpoint": checkpoint_payload,
                }
            ),
            "run_dir": str(run_json_path.parent.resolve()),
        }
        records.append((last_update, record))

    records.sort(key=lambda item: item[0])
    return [record for _, record in records]


def classify_recovery_action(record: dict[str, Any]) -> str:
    phase = str(record.get("phase") or "").strip().lower()
    checkpoint = record.get("checkpoint")
    checkpoint_stage = ""
    resume_stage = ""
    if isinstance(checkpoint, dict):
        checkpoint_stage = str(checkpoint.get("stage") or "").strip().lower()
        resume_stage = str(checkpoint.get("resume_stage") or "").strip().lower()

    effective_stage = resume_stage or checkpoint_stage

    if phase in TERMINAL_PHASES:
        return "mark_failed_requires_manual_review"
    if phase in {"queued", "planning"}:
        return "redispatch_full_run"
    if phase == "validating":
        return "redispatch_from_validation"
    if phase == "healing":
        if effective_stage == "validation":
            return "redispatch_from_validation"
        if resume_stage == "execution":
            return "redispatch_from_execution"
        if effective_stage in {"queued", "planning", "replanning"}:
            return "redispatch_full_run"
        return "mark_failed_requires_manual_review"
    if phase == "running":
        if effective_stage == "validation":
            return "redispatch_from_validation"
        return "redispatch_from_execution"
    return "mark_failed_requires_manual_review"


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
