from __future__ import annotations

from schemas.agent import RunEvent, RunPhase, RunStatus, RunTrigger, RunTriggerType
from schemas.fusion import JobType
from services.agent_run_service import build_run_inspection_digest, derive_run_inspection_digest


def _build_failed_status() -> RunStatus:
    return RunStatus(
        run_id="run-inspection-failed",
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="need building data"),
        phase=RunPhase.failed,
        progress=62,
        target_crs="EPSG:32643",
        error="parameter out of range",
        current_step=3,
        failure_summary="parameter out of range | failure_category=PARAM_OUT_OF_RANGE | suggested_action=replan",
        checkpoint={"stage": "execution", "current_step": 3, "plan_revision": 1},
        created_at="2026-05-13T00:00:00+00:00",
        updated_at="2026-05-13T00:01:00+00:00",
    )


def test_build_run_inspection_digest_exposes_root_cause_and_next_action() -> None:
    digest = build_run_inspection_digest(
        current_phase="planning",
        failed_step="step 3",
        root_cause="PARAM_OUT_OF_RANGE",
        recoverability="replan",
        next_operator_action="adjust bound and rerun",
    )

    assert digest["root_cause"] == "PARAM_OUT_OF_RANGE"
    assert digest["next_operator_action"] == "adjust bound and rerun"


def test_derive_run_inspection_digest_uses_failure_details_for_operator_guidance() -> None:
    status = _build_failed_status()
    events = [
        RunEvent(
            timestamp="2026-05-13T00:01:00+00:00",
            kind="step_failed",
            phase=RunPhase.running,
            message="step failed",
            plan_revision=1,
            progress=62,
            attempt_no=1,
            current_step=3,
            details={
                "root_cause": "PARAM_OUT_OF_RANGE",
                "failure_category": "PARAM_OUT_OF_RANGE",
                "suggested_action": "replan",
                "action": "replan",
                "recoverable": True,
            },
        )
    ]

    digest = derive_run_inspection_digest(status, events)

    assert digest["current_phase"] == "execution"
    assert digest["failed_step"] == "step 3"
    assert digest["root_cause"] == "PARAM_OUT_OF_RANGE"
    assert digest["recoverability"] == "replan"
    assert digest["next_operator_action"] == "adjust bound and rerun"
