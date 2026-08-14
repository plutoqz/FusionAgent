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


def _water_plan(task_kind: str) -> WorkflowPlan:
    semantics = {
        "water_polygon": {
            "task_id": "task.water.fusion",
            "algorithm_id": "algo.fusion.water_polygon.priority_merge.v2",
            "input_data_source_id": "catalog.flood.water",
            "input_data_type_id": "dt.water.bundle",
            "output_data_type_id": "dt.water.fused",
        },
        "waterways": {
            "task_id": "task.waterways.fusion",
            "algorithm_id": "algo.fusion.waterways.conflation.v7",
            "input_data_source_id": "catalog.flood.waterways",
            "input_data_type_id": "dt.waterways.bundle",
            "output_data_type_id": "dt.waterways.fused",
        },
    }[task_kind]
    plan = _plan().model_copy(deep=True)
    task = plan.tasks[0]
    task.task_id = semantics["task_id"]
    task.algorithm_id = semantics["algorithm_id"]
    task.input.data_source_id = semantics["input_data_source_id"]
    task.input.data_type_id = semantics["input_data_type_id"]
    task.output.data_type_id = semantics["output_data_type_id"]
    plan.product_contract = None
    plan.trigger.disaster_type = "flood"
    return plan


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


@pytest.mark.parametrize("task_kind", ["water_polygon", "waterways"])
def test_frozen_plan_validation_accepts_water_task_kinds_for_water_job(task_kind: str) -> None:
    plan = _water_plan(task_kind)

    validated, actual = AgentRunService._validate_frozen_plan_input(
        request=_request(job_type=JobType.water, disaster_type="flood"),
        frozen_plan=plan,
        expected_sha256=_workflow_plan_semantic_hash(plan),
    )

    assert actual == _workflow_plan_semantic_hash(plan)
    assert validated == plan


def test_frozen_plan_validation_rejects_water_task_for_road_job() -> None:
    plan = _water_plan("waterways")
    with pytest.raises(ValueError, match="FROZEN_PLAN_JOB_TYPE_MISMATCH"):
        AgentRunService._validate_frozen_plan_input(
            request=_request(job_type=JobType.road, disaster_type="flood"),
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
    monkeypatch.setattr(service, "_update_status", lambda *args, **kwargs: None)
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
    persisted = WorkflowPlan.model_validate(
        json.loads((tmp_path / "runs" / "frozen-plan-test" / "plan.json").read_text(encoding="utf-8"))
    )
    assert _workflow_plan_semantic_hash(persisted) == expected


def test_plan_persistence_never_mutates_caller(tmp_path: Path) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs", max_workers=1)
    plan = _plan()
    expected = _workflow_plan_semantic_hash(plan)
    try:
        service._persist_plan(tmp_path / "persisted-plan.json", plan)
    finally:
        service.shutdown()

    assert _workflow_plan_semantic_hash(plan) == expected
    persisted = WorkflowPlan.model_validate(
        json.loads((tmp_path / "persisted-plan.json").read_text(encoding="utf-8"))
    )
    assert "grounding_report" in persisted.context


def test_create_run_preserves_frozen_plan_through_persistence(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs", max_workers=1)
    plan = _plan()
    expected = _workflow_plan_semantic_hash(plan)
    captured: dict[str, str] = {}

    def capture_execute_run(**kwargs) -> None:
        captured["sha256"] = _workflow_plan_semantic_hash(kwargs["frozen_plan"])

    monkeypatch.setattr(service, "execute_run", capture_execute_run)
    try:
        status = service.create_run(
            request=_request(),
            osm_zip_name=None,
            osm_zip_bytes=None,
            ref_zip_name=None,
            ref_zip_bytes=None,
            frozen_plan=plan,
            frozen_plan_sha256=expected,
        )
    finally:
        service.shutdown()

    persisted = WorkflowPlan.model_validate(
        json.loads(
            (tmp_path / "runs" / status.run_id / "frozen_plan_input.json").read_text(encoding="utf-8")
        )
    )
    assert captured["sha256"] == expected
    assert _workflow_plan_semantic_hash(persisted) == expected
