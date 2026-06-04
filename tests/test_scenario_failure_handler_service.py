from __future__ import annotations

from services.scenario_failure_handler_service import ScenarioFailureHandlerService


def test_failure_handler_builds_recoverable_download_failure_record() -> None:
    record = ScenarioFailureHandlerService().build_child_failure_record(
        scenario_id="scenario-1",
        child_result={
            "run_id": "run-poi",
            "job_type": "poi",
            "task_kind": "poi",
            "task_family": "poi",
            "phase": "failed",
            "error": "SOURCE_DOWNLOAD_FAILED: timeout",
        },
        recovery_hint={
            "recoverable": True,
            "recovery_action": "retry_source_download",
            "operator_action": "retry",
        },
    )

    assert record.scenario_id == "scenario-1"
    assert record.task_kind == "poi"
    assert record.recovery_state == "retry_scheduled"
    assert record.next_action == "retry_source_download"
    assert record.recoverable is True


def test_failure_handler_marks_manual_review_when_not_recoverable() -> None:
    record = ScenarioFailureHandlerService().build_child_failure_record(
        scenario_id="scenario-1",
        child_result={
            "run_id": "run-waterways",
            "job_type": "water",
            "task_kind": "waterways",
            "task_family": "water",
            "phase": "failed",
            "error": "schema mismatch",
        },
        recovery_hint={"recoverable": False, "recovery_action": "none", "operator_action": "manual_review"},
    )

    assert record.recovery_state == "blocked"
    assert record.next_action == "manual_review"
