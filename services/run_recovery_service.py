from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from schemas.failure_taxonomy import classify_failure_category

TERMINAL_PHASES = {"succeeded"}
RECOVERABLE_ACTIONS = {
    "redispatch_full_run",
    "redispatch_from_validation",
    "redispatch_from_execution",
}
RECOVERABLE_FAILURE_CATEGORIES = {
    "SOURCE_DOWNLOAD_FAILED",
    "SOURCE_MISSING",
    "SOURCE_CORRUPTED",
    "CRS_MISMATCH",
    "ALGO_TIMEOUT",
}


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

        phase = str(raw_record.get("phase") or "").strip().lower()
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
        failure_category = _failure_category(raw_record)
        recovery_action = classify_recovery_action(
            {
                "phase": phase,
                "checkpoint": checkpoint_payload,
                "failure_summary": raw_record.get("failure_summary"),
                "error": raw_record.get("error"),
            }
        )
        if recovery_action not in RECOVERABLE_ACTIONS:
            continue
        record = {
            "run_id": str(raw_record.get("run_id") or run_json_path.parent.name),
            "phase": phase,
            "updated_at": updated_at_text or last_update.isoformat(),
            "checkpoint": checkpoint_payload,
            "recovery_action": recovery_action,
            "run_dir": str(run_json_path.parent.resolve()),
        }
        if failure_category is not None:
            record["failure_category"] = failure_category
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
    if phase == "failed":
        return _failed_run_recovery_action(record, effective_stage=effective_stage)
    checkpoint_action = _checkpoint_recovery_action(phase, effective_stage=effective_stage, resume_stage=resume_stage)
    if checkpoint_action is not None:
        return checkpoint_action
    return "mark_failed_requires_manual_review"


def build_recovery_hint(run_payload: dict[str, Any]) -> dict[str, Any]:
    checkpoint = run_payload.get("checkpoint")
    if not isinstance(checkpoint, dict):
        checkpoint = {}
    failure_category = _failure_category(run_payload)
    action = classify_recovery_action(run_payload)
    recoverable = action in RECOVERABLE_ACTIONS
    reason = "checkpoint_recoverable" if recoverable else "terminal_or_fresh_run"
    if recoverable and failure_category is not None:
        reason = "failure_category_recoverable"
    elif not recoverable and str(run_payload.get("phase") or "").strip().lower() == "failed":
        reason = "manual_review_required"
    phase = str(run_payload.get("phase") or "").strip().lower()
    operator_action = _operator_action(action, recoverable=recoverable, phase=phase)
    payload = {
        "recoverable": recoverable,
        "recovery_action": action if recoverable else "none",
        "operator_action": operator_action,
        "reason": reason,
        "checkpoint": dict(checkpoint),
    }
    if failure_category is not None:
        payload["failure_category"] = failure_category
    classification_evidence = _classification_evidence(
        run_payload,
        checkpoint=dict(checkpoint),
        failure_category=failure_category,
        recovery_action=action,
    )
    if classification_evidence:
        payload["classification_evidence"] = classification_evidence
    return payload


def _operator_action(action: str, *, recoverable: bool, phase: str) -> str:
    if action == "redispatch_from_execution":
        return "no manual action required; recovery worker can redispatch from execution"
    if recoverable:
        return "no manual action required; recovery worker can redispatch"
    if action == "mark_failed_requires_manual_review" and phase == "failed":
        return "manual review required before rerun"
    return "no operator action available"


def _classification_evidence(
    run_payload: dict[str, Any],
    *,
    checkpoint: dict[str, Any],
    failure_category: str | None,
    recovery_action: str,
) -> dict[str, Any]:
    phase = str(run_payload.get("phase") or "").strip().lower()
    checkpoint_stage = str(checkpoint.get("stage") or "").strip().lower()
    resume_stage = str(checkpoint.get("resume_stage") or "").strip().lower()
    effective_stage = resume_stage or checkpoint_stage
    evidence: dict[str, Any] = {
        "phase": phase,
        "checkpoint_stage": checkpoint_stage,
        "resume_stage": resume_stage,
        "effective_stage": effective_stage,
        "recovery_action": recovery_action,
    }
    if failure_category is not None:
        evidence["failure_category"] = failure_category
        evidence["source"] = _failure_category_source(run_payload)
    return evidence


def _failure_category_source(record: dict[str, Any]) -> str:
    summary = str(record.get("failure_summary") or "").strip()
    error = str(record.get("error") or "").strip()
    if summary:
        return "failure_summary"
    if error:
        return "error"
    return "none"


def _checkpoint_recovery_action(
    phase: str,
    *,
    effective_stage: str,
    resume_stage: str,
) -> str | None:
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
        return None
    if phase == "running":
        if effective_stage == "validation":
            return "redispatch_from_validation"
        return "redispatch_from_execution"
    return None


def _failed_run_recovery_action(record: dict[str, Any], *, effective_stage: str) -> str:
    failure_category = _failure_category(record)
    if failure_category not in RECOVERABLE_FAILURE_CATEGORIES:
        return "mark_failed_requires_manual_review"
    if failure_category == "CRS_MISMATCH":
        return "redispatch_from_validation"
    if effective_stage in {"queued", "planning", "replanning"}:
        return "redispatch_full_run"
    if effective_stage == "validation":
        return "redispatch_from_validation"
    return "redispatch_from_execution"


def _failure_category(record: dict[str, Any]) -> str | None:
    summary = str(record.get("failure_summary") or "").strip()
    error = str(record.get("error") or "").strip()
    if not summary and not error:
        return None
    return classify_failure_category(summary or error)


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
