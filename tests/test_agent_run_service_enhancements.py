from pathlib import Path
from zipfile import ZipFile

from schemas.agent import (
    RepairRecord,
    RunCreateRequest,
    RunPhase,
    RunStatus,
    RunTrigger,
    RunTriggerType,
    ValidationReport,
    WorkflowPlan,
    WorkflowTask,
    WorkflowTaskInput,
    WorkflowTaskOutput,
)
from schemas.fusion import JobType
from services.agent_run_service import AgentRunService


def _write_dummy_zip(path: Path) -> bytes:
    with ZipFile(path, "w") as zf:
        zf.writestr("dummy.shp", b"shp")
        zf.writestr("dummy.shx", b"shx")
        zf.writestr("dummy.dbf", b"dbf")
    return path.read_bytes()


def test_agent_run_service_updates_status_and_records_feedback(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")

    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp, fused_shp]:
        path.write_text("dummy", encoding="utf-8")

    plan = WorkflowPlan(
        workflow_id="wf_service",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        context={
            "intent": {"job_type": "building"},
            "retrieval": {"candidate_patterns": [{"pattern_id": "wp.flood.building.default"}]},
            "selection_reason": "initial",
            "llm_provider": "mock",
            "plan_revision": 1,
        },
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id="algo.fusion.building.v1",
                input=WorkflowTaskInput(data_type_id="dt.building.bundle", data_source_id="upload.bundle", parameters={}),
                output=WorkflowTaskOutput(data_type_id="dt.building.fused", description=""),
                depends_on=[],
                is_transform=False,
                kg_validated=True,
                alternatives=["algo.fusion.building.safe"],
            )
        ],
        expected_output="building result",
        validation=ValidationReport(valid=True, inserted_transform_steps=0, issues=[]),
    )

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    def fake_execute_plan(*, plan, context, repair_records, **_kwargs):
        repair_records.append(
            RepairRecord(
                attempt_no=1,
                strategy="alternative_algorithm",
                step=1,
                message="Recovered with safe algorithm",
                success=True,
                timestamp="2026-04-01T00:00:00+00:00",
                reason_code="alternative_algorithm_succeeded",
                from_algorithm="algo.fusion.building.v1",
                to_algorithm="algo.fusion.building.safe",
            )
        )
        return fused_shp

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)
    artifact_zip.write_bytes(b"zip")

    osm_zip = tmp_path / "osm.zip"
    ref_zip = tmp_path / "ref.zip"
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        target_crs="EPSG:32643",
        field_mapping={},
        debug=False,
    )

    status = service.create_run(
        request=request,
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(osm_zip),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(ref_zip),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert latest.plan_revision == 1
    assert latest.attempt_no == 1
    assert latest.healing_summary["successful_repairs"] == 1
    assert latest.healing_summary["last_reason_code"] == "alternative_algorithm_succeeded"
    assert service.kg_repo.feedback_history[-1].pattern_id == "wp.flood.building.default"


def test_update_status_loads_run_from_disk_when_worker_process_is_fresh(tmp_path: Path) -> None:
    base_dir = tmp_path / "runs"
    run_status = RunStatus(
        run_id="run-from-disk",
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        phase=RunPhase.queued,
        progress=0,
        target_crs="EPSG:32643",
        debug=False,
        error=None,
        log_path=str(base_dir / "run-from-disk" / "logs" / "run.log"),
        plan_path=None,
        validation_path=None,
        artifact=None,
        repair_records=[],
        current_step=None,
        attempt_no=0,
        healing_summary={},
        failure_summary=None,
        plan_revision=0,
        created_at="2026-04-02T00:00:00+00:00",
        started_at=None,
        finished_at=None,
    )

    writer = AgentRunService(base_dir=base_dir)
    writer._persist_status(run_status)

    worker_side = AgentRunService(base_dir=base_dir)
    worker_side._runs.clear()

    worker_side._update_status(
        "run-from-disk",
        RunPhase.planning,
        progress=5,
        started_at="2026-04-02T00:00:01+00:00",
    )

    updated = worker_side.get_run("run-from-disk")
    assert updated is not None
    assert updated.phase == RunPhase.planning
    assert updated.progress == 5
    assert updated.started_at == "2026-04-02T00:00:01+00:00"


def test_get_run_refreshes_stale_cached_status_from_disk(tmp_path: Path) -> None:
    base_dir = tmp_path / "runs"

    api_side = AgentRunService(base_dir=base_dir)
    worker_side = AgentRunService(base_dir=base_dir)

    run_status = RunStatus(
        run_id="shared-run",
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        phase=RunPhase.queued,
        progress=0,
        target_crs="EPSG:32643",
        debug=False,
        error=None,
        log_path=str(base_dir / "shared-run" / "logs" / "run.log"),
        plan_path=None,
        validation_path=None,
        artifact=None,
        repair_records=[],
        current_step=None,
        attempt_no=0,
        healing_summary={},
        failure_summary=None,
        plan_revision=0,
        created_at="2026-04-02T00:00:00+00:00",
        started_at=None,
        finished_at=None,
    )

    api_side._persist_status(run_status)
    api_side._runs["shared-run"] = run_status

    worker_side._update_status(
        "shared-run",
        RunPhase.failed,
        progress=100,
        error="RuntimeError: boom",
        finished_at="2026-04-02T00:00:02+00:00",
        failure_summary="RuntimeError: boom",
    )

    refreshed = api_side.get_run("shared-run")
    assert refreshed is not None
    assert refreshed.phase == RunPhase.failed
    assert refreshed.error == "RuntimeError: boom"
    assert refreshed.finished_at == "2026-04-02T00:00:02+00:00"
