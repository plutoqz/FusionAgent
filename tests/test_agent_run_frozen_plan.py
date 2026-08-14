import json
from pathlib import Path

import pytest

from schemas.agent import RunCreateRequest, RunInputStrategy, RunTrigger, RunTriggerType, WorkflowPlan
from schemas.fusion import JobType
from services.agent_run_service import AgentRunService, _workflow_plan_semantic_hash


FREEZE_ROOT = (
    Path(__file__).parents[1]
    / "docs"
    / "current"
    / "evidence"
    / "p4-planning-e2e"
    / "2026-08-14-c04-road-protocol-freeze-v1"
)


def _plan() -> WorkflowPlan:
    return WorkflowPlan.model_validate(json.loads((FREEZE_ROOT / "workflow_plan.json").read_text(encoding="utf-8")))


def _request(*, job_type: JobType = JobType.road, disaster_type: str = "typhoon") -> RunCreateRequest:
    return RunCreateRequest(
        job_type=job_type,
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content="C04 frozen road execution",
            disaster_type=disaster_type,
            spatial_extent="bbox(-67.17,10.38,-66.86,10.57)",
        ),
        target_crs="EPSG:32619",
        input_strategy=RunInputStrategy.task_driven_auto,
    )


def test_frozen_plan_validation_returns_deep_copy_with_exact_hash() -> None:
    plan = _plan()
    expected = _workflow_plan_semantic_hash(plan)

    validated, actual = AgentRunService._validate_frozen_plan_input(
        request=_request(),
        frozen_plan=plan,
        expected_sha256=expected,
    )

    assert actual == expected
    assert validated == plan
    assert validated is not plan


def test_frozen_plan_validation_rejects_hash_mismatch() -> None:
    with pytest.raises(ValueError, match="FROZEN_PLAN_HASH_MISMATCH"):
        AgentRunService._validate_frozen_plan_input(
            request=_request(),
            frozen_plan=_plan(),
            expected_sha256="sha256:" + "0" * 64,
        )


def test_frozen_plan_validation_rejects_job_type_mismatch() -> None:
    plan = _plan()
    with pytest.raises(ValueError, match="FROZEN_PLAN_JOB_TYPE_MISMATCH"):
        AgentRunService._validate_frozen_plan_input(
            request=_request(job_type=JobType.building),
            frozen_plan=plan,
            expected_sha256=_workflow_plan_semantic_hash(plan),
        )


def test_frozen_plan_validation_rejects_disaster_mismatch() -> None:
    plan = _plan()
    with pytest.raises(ValueError, match="FROZEN_PLAN_DISASTER_MISMATCH"):
        AgentRunService._validate_frozen_plan_input(
            request=_request(disaster_type="flood"),
            frozen_plan=plan,
            expected_sha256=_workflow_plan_semantic_hash(plan),
        )


def test_frozen_planning_stage_does_not_mutate_hash_locked_plan(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs", max_workers=1)
    plan = _plan()
    expected = _workflow_plan_semantic_hash(plan)
    persisted: list[WorkflowPlan] = []
    monkeypatch.setattr(service, "_update_status", lambda *args, **kwargs: None)
    monkeypatch.setattr(service, "_persist_plan", lambda path, value: persisted.append(value.model_copy(deep=True)))
    try:
        result = service.run_frozen_planning_stage(
            run_id="frozen-plan-test",
            request=_request(),
            frozen_plan=plan,
            expected_sha256=expected,
        )
    finally:
        service.shutdown()

    assert _workflow_plan_semantic_hash(result) == expected
    assert [_workflow_plan_semantic_hash(value) for value in persisted] == [expected]
