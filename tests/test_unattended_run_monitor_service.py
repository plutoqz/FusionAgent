from __future__ import annotations

from services.unattended_run_monitor_service import (
    build_unattended_runtime_snapshot,
    classify_unattended_readiness,
)


def test_classify_unattended_readiness_ready_when_schedule_inbox_and_recovery_have_evidence() -> None:
    snapshot = build_unattended_runtime_snapshot(
        scheduled_tick_result={
            "configured": 2,
            "created": 2,
            "run_ids": ["run-a", "run-b"],
            "errors": [],
            "spec_results": [
                {"index": 1, "status": "created", "input_strategy": "task_driven_auto", "run_id": "run-a"},
                {"index": 2, "status": "created", "input_strategy": "uploaded", "run_id": "run-b"},
            ],
        },
        inbox_result={"processed": ["scenario-a"], "failed": [], "idempotent": []},
        recovery_tick_result={"enabled": True, "attempted": 1, "recovered": 1, "failed": 0, "records": []},
        recent_runs=[
            {"run_id": "run-a", "phase": "succeeded"},
            {"run_id": "run-b", "phase": "succeeded"},
        ],
    )

    assert snapshot["readiness"] == "ready"
    assert snapshot["unattended_modes"]["scheduled_task_driven_auto"] is True
    assert snapshot["unattended_modes"]["local_inbox"] is True
    assert snapshot["unattended_modes"]["recovery_tick"] is True
    assert snapshot["manual_intervention_required"] is False
    assert (
        snapshot["long_running_boundary"]
        == "process supervision and external scheduler uptime are environment responsibilities"
    )


def test_classify_unattended_readiness_degraded_when_recovery_disabled_or_errors_present() -> None:
    readiness = classify_unattended_readiness(
        scheduled_errors=["scheduled_spec_1: ValueError: bad source"],
        inbox_failed_count=1,
        recovery_enabled=False,
        recovery_failed_count=0,
    )

    assert readiness == "degraded"
