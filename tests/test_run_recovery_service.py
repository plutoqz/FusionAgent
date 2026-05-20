from __future__ import annotations

import json
from pathlib import Path

from services.agent_run_service import AgentRunService
from services.run_recovery_service import (
    build_recovery_hint,
    classify_recovery_action,
    collect_recoverable_runs,
)


def _write_run_record(runs_root: Path, run_id: str, payload: dict[str, object]) -> Path:
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return run_dir


def test_collect_recoverable_runs_returns_stale_running_run_with_checkpoint(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_dir = _write_run_record(
        runs_root,
        "run-stale",
        {
            "run_id": "run-stale",
            "phase": "running",
            "job_type": "building",
            "updated_at": "2026-04-23T00:00:00+00:00",
            "checkpoint": {
                "stage": "execution",
                "plan_revision": 2,
                "current_step": 4,
                "attempt_no": 1,
            },
        },
    )

    records = collect_recoverable_runs(
        runs_root=runs_root,
        stale_after_seconds=300,
    )

    assert len(records) == 1
    assert records[0] == {
        "run_id": "run-stale",
        "phase": "running",
        "updated_at": "2026-04-23T00:00:00+00:00",
        "checkpoint": {
            "stage": "execution",
            "plan_revision": 2,
            "current_step": 4,
            "attempt_no": 1,
        },
        "recovery_action": "redispatch_from_execution",
        "run_dir": str(run_dir.resolve()),
    }


def test_collect_recoverable_runs_skips_terminal_or_fresh_runs(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    _write_run_record(
        runs_root,
        "run-succeeded",
        {
            "run_id": "run-succeeded",
            "phase": "succeeded",
            "job_type": "building",
            "updated_at": "2026-04-23T00:00:00+00:00",
            "checkpoint": {"stage": "execution"},
        },
    )
    _write_run_record(
        runs_root,
        "run-fresh",
        {
            "run_id": "run-fresh",
            "phase": "validating",
            "job_type": "building",
            "updated_at": "3026-04-23T00:00:00+00:00",
            "checkpoint": {"stage": "validation"},
        },
    )

    records = collect_recoverable_runs(
        runs_root=runs_root,
        stale_after_seconds=300,
    )

    assert records == []


def test_classify_recovery_action_uses_phase_and_checkpoint_stage() -> None:
    assert classify_recovery_action({"phase": "queued", "checkpoint": {}}) == "redispatch_full_run"
    assert classify_recovery_action({"phase": "planning", "checkpoint": {"stage": "planning"}}) == "redispatch_full_run"
    assert (
        classify_recovery_action({"phase": "running", "checkpoint": {"stage": "validation"}})
        == "redispatch_from_validation"
    )
    assert (
        classify_recovery_action({"phase": "healing", "checkpoint": {"stage": "validation", "plan_revision": 2}})
        == "redispatch_from_validation"
    )
    assert (
        classify_recovery_action({"phase": "running", "checkpoint": {"stage": "execution"}})
        == "redispatch_from_execution"
    )
    assert (
        classify_recovery_action({"phase": "healing", "checkpoint": {"stage": "execution"}})
        == "mark_failed_requires_manual_review"
    )
    assert (
        classify_recovery_action({"phase": "failed", "checkpoint": {"stage": "execution"}})
        == "mark_failed_requires_manual_review"
    )
    assert (
        classify_recovery_action({"phase": "mystery", "checkpoint": {"stage": "execution"}})
        == "mark_failed_requires_manual_review"
    )


def test_agent_run_service_collect_recoverable_runs_exposes_scanner(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    _write_run_record(
        runs_root,
        "run-service",
        {
            "run_id": "run-service",
            "phase": "validating",
            "job_type": "building",
            "updated_at": "2026-04-23T00:00:00+00:00",
            "checkpoint": {"stage": "validation", "plan_revision": 1},
        },
    )

    service = AgentRunService(base_dir=runs_root)
    try:
        records = service.collect_recoverable_runs(stale_after_seconds=300)
    finally:
        service.shutdown()

    assert len(records) == 1
    assert records[0]["run_id"] == "run-service"
    assert records[0]["recovery_action"] == "redispatch_from_validation"


def test_collect_recoverable_runs_treats_healing_validation_checkpoint_as_recoverable(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    _write_run_record(
        runs_root,
        "run-healing",
        {
            "run_id": "run-healing",
            "phase": "healing",
            "job_type": "building",
            "updated_at": "2026-04-23T00:00:00+00:00",
            "checkpoint": {
                "stage": "validation",
                "plan_revision": 2,
                "current_step": 1,
                "attempt_no": 3,
            },
        },
    )

    records = collect_recoverable_runs(
        runs_root=runs_root,
        stale_after_seconds=300,
    )

    assert len(records) == 1
    assert records[0]["run_id"] == "run-healing"
    assert records[0]["recovery_action"] == "redispatch_from_validation"


def test_build_recovery_hint_marks_terminal_runs_not_recoverable() -> None:
    hint = build_recovery_hint(
        {
            "phase": "succeeded",
            "checkpoint": {"stage": "execution"},
            "updated_at": "2026-05-20T00:00:00+00:00",
        }
    )

    assert hint == {
        "recoverable": False,
        "recovery_action": "none",
        "reason": "terminal_or_fresh_run",
        "checkpoint": {"stage": "execution"},
    }


def test_build_recovery_hint_uses_checkpoint_stage_for_running_run() -> None:
    hint = build_recovery_hint(
        {
            "phase": "running",
            "checkpoint": {"stage": "execution", "plan_revision": 1, "current_step": 2},
            "updated_at": "2026-05-20T00:00:00+00:00",
        }
    )

    assert hint["recoverable"] is True
    assert hint["recovery_action"] == "redispatch_from_execution"
    assert hint["checkpoint"]["current_step"] == 2
