from __future__ import annotations

import json
from pathlib import Path

from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import RunCreateRequest, RunInputStrategy, RunPhase, RunStatus, RunTrigger, RunTriggerType
from schemas.fusion import JobType
from services.agent_run_service import AgentRunService
from services.run_recovery_service import (
    build_recovery_hint,
    classify_recovery_action,
    collect_recoverable_runs,
)
from services.runtime_contract_service import RuntimeContractService


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


def test_collect_recoverable_runs_includes_failed_timeout_run_with_recovery_action(
    tmp_path: Path,
) -> None:
    runs_root = tmp_path / "runs"
    _write_run_record(
        runs_root,
        "run-failed-timeout",
        {
            "run_id": "run-failed-timeout",
            "phase": "failed",
            "job_type": "building",
            "updated_at": "2026-04-23T00:00:00+00:00",
            "checkpoint": {
                "stage": "execution",
                "plan_revision": 2,
                "current_step": 4,
            },
            "failure_summary": (
                "download timed out while materializing inputs"
                " | failure_category=ALGO_TIMEOUT"
            ),
        },
    )

    records = collect_recoverable_runs(
        runs_root=runs_root,
        stale_after_seconds=300,
    )

    assert len(records) == 1
    assert records[0]["run_id"] == "run-failed-timeout"
    assert records[0]["recovery_action"] == "redispatch_from_execution"
    assert records[0]["failure_category"] == "ALGO_TIMEOUT"


def test_collect_recoverable_runs_marks_algorithm_state_drift_for_manual_review(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_dir = _write_run_record(
        runs_root,
        "run-stale-deprecated",
        {
            "run_id": "run-stale-deprecated",
            "phase": "running",
            "job_type": "road",
            "updated_at": "2026-04-23T00:00:00+00:00",
            "checkpoint": {"stage": "execution", "plan_revision": 1},
        },
    )
    (run_dir / "plan.json").write_text(
        json.dumps(
            {
                "workflow_id": "wf-deprecated",
                "trigger": {"type": "user_query", "content": "road"},
                "tasks": [
                    {
                        "step": 1,
                        "name": "deprecated_road",
                        "description": "deprecated",
                        "algorithm_id": "algo.fusion.road.v1",
                        "input": {"data_type_id": "dt.road.bundle", "data_source_id": "catalog.flood.road"},
                        "output": {"data_type_id": "dt.road.fused"},
                    }
                ],
                "expected_output": "road",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    records = collect_recoverable_runs(
        runs_root=runs_root,
        stale_after_seconds=300,
        include_manual_review=True,
        runtime_contract_service=RuntimeContractService(InMemoryKGRepository()),
    )

    assert len(records) == 1
    assert records[0]["run_id"] == "run-stale-deprecated"
    assert records[0]["recovery_action"] == "mark_failed_requires_manual_review"
    assert records[0]["algorithm_state"]["reason_code"] == "DEPRECATED_ALGORITHM"


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
        "operator_action": "no operator action available",
        "reason": "terminal_or_fresh_run",
        "classification_evidence": {
            "phase": "succeeded",
            "checkpoint_stage": "execution",
            "resume_stage": "",
            "effective_stage": "execution",
            "recovery_action": "mark_failed_requires_manual_review",
        },
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


def test_classify_recovery_action_uses_failure_category_for_failed_runs() -> None:
    assert (
        classify_recovery_action(
            {
                "phase": "failed",
                "checkpoint": {"stage": "validation"},
                "failure_summary": "fault=crs_mismatch",
            }
        )
        == "redispatch_from_validation"
    )
    assert (
        classify_recovery_action(
            {
                "phase": "failed",
                "checkpoint": {"stage": "execution"},
                "error": "download timed out while materializing inputs",
            }
        )
        == "redispatch_from_execution"
    )
    assert (
        classify_recovery_action(
            {
                "phase": "failed",
                "checkpoint": {"stage": "execution"},
                "error": "semantically empty suspect output",
            }
        )
        == "mark_failed_requires_manual_review"
    )


def test_build_recovery_hint_marks_failed_timeout_run_recoverable() -> None:
    hint = build_recovery_hint(
        {
            "phase": "failed",
            "checkpoint": {"stage": "execution", "plan_revision": 1, "current_step": 2},
            "failure_summary": "download timed out while materializing inputs | failure_category=ALGO_TIMEOUT",
            "updated_at": "2026-05-20T00:00:00+00:00",
        }
    )

    assert hint == {
        "recoverable": True,
        "recovery_action": "redispatch_from_execution",
        "operator_action": "no manual action required; recovery worker can redispatch from execution",
        "reason": "failure_category_recoverable",
        "failure_category": "ALGO_TIMEOUT",
        "classification_evidence": {
            "phase": "failed",
            "checkpoint_stage": "execution",
            "resume_stage": "",
            "failure_category": "ALGO_TIMEOUT",
            "effective_stage": "execution",
            "recovery_action": "redispatch_from_execution",
            "source": "failure_summary",
        },
        "checkpoint": {"stage": "execution", "plan_revision": 1, "current_step": 2},
    }


def test_build_recovery_hint_includes_operator_action_for_recoverable_download_failure() -> None:
    hint = build_recovery_hint(
        {
            "phase": "failed",
            "checkpoint": {"stage": "execution", "resume_stage": "execution"},
            "failure_summary": "download timed out while materializing inputs | failure_category=SOURCE_DOWNLOAD_FAILED",
        }
    )

    assert hint["recoverable"] is True
    assert hint["recovery_action"] == "redispatch_from_execution"
    assert hint["operator_action"] == "no manual action required; recovery worker can redispatch from execution"
    assert hint["classification_evidence"]["failure_category"] == "SOURCE_DOWNLOAD_FAILED"
    assert hint["classification_evidence"]["checkpoint_stage"] == "execution"
    assert hint["classification_evidence"]["resume_stage"] == "execution"


def test_build_recovery_hint_marks_manual_review_failures_with_operator_action() -> None:
    hint = build_recovery_hint(
        {
            "phase": "failed",
            "checkpoint": {"stage": "execution", "plan_revision": 1, "current_step": 2},
            "error": "semantically empty suspect output",
            "updated_at": "2026-05-20T00:00:00+00:00",
        }
    )

    assert hint == {
        "recoverable": False,
        "recovery_action": "none",
        "operator_action": "manual review required before rerun",
        "reason": "manual_review_required",
        "failure_category": "SUSPECT_OUTPUT",
        "classification_evidence": {
            "phase": "failed",
            "checkpoint_stage": "execution",
            "resume_stage": "",
            "failure_category": "SUSPECT_OUTPUT",
            "effective_stage": "execution",
            "recovery_action": "mark_failed_requires_manual_review",
            "source": "error",
        },
        "checkpoint": {"stage": "execution", "plan_revision": 1, "current_step": 2},
    }


def test_agent_run_service_resume_full_run_reuses_existing_request(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base_dir = tmp_path / "runs"
    service = AgentRunService(base_dir=base_dir)
    run_dir = base_dir / "run-resume"
    for name in ["input", "intermediate", "output", "logs"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    request = RunCreateRequest(
        job_type=JobType.road,
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content="fuse road",
            spatial_extent="bbox(0,0,1,1)",
        ),
        input_strategy=RunInputStrategy.task_driven_auto,
    )
    (run_dir / "request.json").write_text(
        json.dumps(request.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )
    status = RunStatus(
        run_id="run-resume",
        job_type=JobType.road,
        trigger=request.trigger,
        phase=RunPhase.running,
        progress=66,
        target_crs="EPSG:4326",
        checkpoint={"stage": "execution", "plan_revision": 1},
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:00+00:00",
    )
    service._persist_status(status)
    captured: dict[str, object] = {}

    def fake_execute_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(service, "execute_run", fake_execute_run)

    try:
        result = service.resume_run_from_checkpoint("run-resume", "redispatch_from_execution")
    finally:
        service.shutdown()

    assert result["run_id"] == "run-resume"
    assert result["recovery_action"] == "redispatch_from_execution"
    assert captured["run_id"] == "run-resume"
    assert captured["request"] == request
    assert captured["intermediate_dir"] == run_dir / "intermediate"
    assert captured["output_dir"] == run_dir / "output"
    assert captured["log_dir"] == run_dir / "logs"


def test_agent_run_service_resume_from_validation_preserves_resume_stage(
    tmp_path: Path,
    monkeypatch,
) -> None:
    base_dir = tmp_path / "runs"
    service = AgentRunService(base_dir=base_dir)
    run_dir = base_dir / "run-resume-validation"
    for name in ["input", "intermediate", "output", "logs"]:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    request = RunCreateRequest(
        job_type=JobType.road,
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content="fuse road",
            spatial_extent="bbox(0,0,1,1)",
        ),
        input_strategy=RunInputStrategy.task_driven_auto,
    )
    (run_dir / "request.json").write_text(
        json.dumps(request.model_dump(mode="json"), ensure_ascii=False),
        encoding="utf-8",
    )
    status = RunStatus(
        run_id="run-resume-validation",
        job_type=JobType.road,
        trigger=request.trigger,
        phase=RunPhase.failed,
        progress=66,
        target_crs="EPSG:4326",
        checkpoint={"stage": "validation", "plan_revision": 1},
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:00+00:00",
        failure_summary="fault=crs_mismatch",
    )
    service._persist_status(status)

    def fake_execute_run(**_kwargs):
        return None

    monkeypatch.setattr(service, "execute_run", fake_execute_run)

    try:
        result = service.resume_run_from_checkpoint("run-resume-validation", "redispatch_from_validation")
    finally:
        service.shutdown()

    assert result["recovery_action"] == "redispatch_from_validation"
    assert result["checkpoint"]["resume_stage"] == "validation"
