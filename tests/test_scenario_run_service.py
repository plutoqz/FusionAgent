from __future__ import annotations

import json
from pathlib import Path
from threading import Event, Lock

import pytest

from schemas.agent import RunEvent, RunPhase, RunStatus, RunTrigger, RunTriggerType, ValidationReport, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from schemas.fusion import JobType
from schemas.scenario import ScenarioPhase, ScenarioRunRequest
from schemas.scenario_checkpoint import ScenarioCheckpoint, ScenarioCheckpointChildRun
from schemas.task_kind import TaskKind
from services.scenario_checkpoint_service import checkpoint_path, write_scenario_checkpoint
from services.scenario_registry_service import ScenarioRegistryService
from services.scenario_run_service import ScenarioRunService, build_child_run_specs


def test_build_child_run_specs_expands_building_and_road_tasks(tmp_path):
    request = ScenarioRunRequest(
        scenario_name="Parakou earthquake",
        trigger_content="fuse building and road data for Parakou, Benin after an earthquake",
        disaster_type="earthquake",
        job_types=[JobType.building, JobType.road],
        output_root=str(tmp_path),
    )

    specs = build_child_run_specs(request)

    assert [spec.job_type for spec in specs] == [JobType.building, JobType.road]
    assert all(spec.disaster_type == "earthquake" for spec in specs)


def test_build_child_run_specs_propagates_spatial_extent(tmp_path):
    request = ScenarioRunRequest(
        scenario_name="Nairobi building",
        trigger_content="need building data for Nairobi, Kenya",
        job_types=[JobType.building],
        output_root=str(tmp_path),
        spatial_extent="bbox(36.79,-1.31,36.81,-1.29)",
    )

    specs = build_child_run_specs(request)

    assert len(specs) == 1
    assert specs[0].spatial_extent == "bbox(36.79,-1.31,36.81,-1.29)"


def test_build_child_run_specs_expands_implicit_flood_bundle_for_chinese_scenario(tmp_path):
    request = ScenarioRunRequest(
        scenario_name="Karachi flood",
        trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
        disaster_type="flood",
        spatial_extent="Karachi, Pakistan",
        output_root=str(tmp_path),
    )

    specs = build_child_run_specs(request)

    assert [spec.task_kind for spec in specs] == [
        TaskKind.building,
        TaskKind.road,
        TaskKind.water_polygon,
        TaskKind.waterways,
        TaskKind.poi,
    ]
    assert [spec.job_type for spec in specs] == [
        JobType.building,
        JobType.road,
        JobType.water,
        JobType.water,
        JobType.poi,
    ]
    assert specs[2].preferred_pattern_id == "wp.flood.water_polygon.default"
    assert specs[3].preferred_pattern_id == "wp.flood.waterways.default"
    assert all(spec.disaster_type == "flood" for spec in specs)
    assert all(spec.spatial_extent == "Karachi, Pakistan" for spec in specs)


def test_scenario_run_service_writes_summary_and_reports(tmp_path):
    service = ScenarioRunService(agent_run_service=_FakeAgentRunService(tmp_path))

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Parakou earthquake",
            trigger_content="fuse building and road data for Parakou, Benin after an earthquake",
            disaster_type="earthquake",
            job_types=[JobType.building, JobType.road],
            output_root=str(tmp_path / "scenarios"),
        )
    )

    scenario_dir = Path(response.output_dir)
    summary = json.loads((scenario_dir / "scenario_summary.json").read_text(encoding="utf-8"))
    assert response.phase == ScenarioPhase.succeeded
    assert response.child_run_ids == ["run-building", "run-road"]
    assert summary["kg_path_traces"]
    assert summary["workflow_traces"]
    assert summary["evaluation"]["agentic_metrics"]["manual_intervention_count"] == 0
    assert (scenario_dir / "scenario_artifact_manifest.json").exists()
    assert (scenario_dir / "documents" / "scenario_report.zh.md").exists()
    assert (scenario_dir / "documents" / "scenario_report.en.md").exists()


def test_scenario_run_service_writes_checkpoint_with_request_specs_and_runs(tmp_path):
    service = ScenarioRunService(agent_run_service=_FakeAgentRunService(tmp_path))

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
            disaster_type="flood",
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    checkpoint_path = Path(response.output_dir) / "scenario_checkpoint.json"
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))

    assert checkpoint_path.exists()
    assert checkpoint["scenario_id"] == response.scenario_id
    assert checkpoint["phase"] == response.phase.value
    assert checkpoint["request"]["scenario_name"] == "Karachi flood"
    assert [item["task_kind"] for item in checkpoint["child_specs"]] == [
        "building",
        "road",
        "water_polygon",
        "waterways",
        "poi",
    ]
    assert [item["task_kind"] for item in checkpoint["child_runs"]] == [
        "building",
        "road",
        "water_polygon",
        "waterways",
        "poi",
    ]
    assert checkpoint["started_at"]
    assert checkpoint["updated_at"]
    assert checkpoint["resume_count"] == 0


def test_scenario_run_service_final_checkpoint_matches_response_and_order(tmp_path):
    service = ScenarioRunService(agent_run_service=_FakeAgentRunService(tmp_path))

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请执行地理空间矢量数据融合。",
            disaster_type="flood",
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    checkpoint = json.loads((Path(response.output_dir) / "scenario_checkpoint.json").read_text(encoding="utf-8"))

    assert checkpoint["phase"] == response.phase.value
    assert checkpoint["resume_count"] == 0
    assert [item["run_id"] for item in checkpoint["child_runs"]] == response.child_run_ids
    assert [item["phase"] for item in checkpoint["child_runs"]] == [RunPhase.succeeded.value] * 5


def test_scenario_checkpoint_phase_stays_running_until_summary_files_are_written(tmp_path, monkeypatch):
    service = ScenarioRunService(agent_run_service=_FakeAgentRunService(tmp_path))

    def fail_summary_write(output_dir, summary):
        raise RuntimeError("summary write interrupted")

    monkeypatch.setattr(ScenarioRunService, "_write_summary_files", staticmethod(fail_summary_write))

    with pytest.raises(RuntimeError, match="summary write interrupted"):
        service.create_scenario_run(
            ScenarioRunRequest(
                scenario_name="Karachi flood",
                trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请执行地理空间矢量数据融合。",
                disaster_type="flood",
                spatial_extent="Karachi, Pakistan",
                output_root=str(tmp_path / "scenarios"),
            )
        )

    scenario_dirs = list((tmp_path / "scenarios").glob("scenario_*"))
    checkpoint = json.loads((scenario_dirs[0] / "scenario_checkpoint.json").read_text(encoding="utf-8"))

    assert checkpoint["phase"] == ScenarioPhase.running.value
    assert checkpoint["children_phase"] == ScenarioPhase.succeeded.value
    assert [item["phase"] for item in checkpoint["child_runs"]] == [RunPhase.succeeded.value] * 5


def test_scenario_checkpoint_records_completed_child_before_later_child_interrupts(tmp_path):
    service = ScenarioRunService(agent_run_service=_InterruptAfterFirstChildAgentRunService(tmp_path))

    with pytest.raises(KeyboardInterrupt, match="process interrupted"):
        service.create_scenario_run(
            ScenarioRunRequest(
                scenario_name="Parakou earthquake",
                trigger_content="fuse building and road data for Parakou, Benin after an earthquake",
                disaster_type="earthquake",
                job_types=[JobType.building, JobType.road],
                output_root=str(tmp_path / "scenarios"),
            )
        )

    scenario_dirs = list((tmp_path / "scenarios").glob("scenario_*"))
    checkpoint = json.loads((scenario_dirs[0] / "scenario_checkpoint.json").read_text(encoding="utf-8"))

    assert checkpoint["phase"] == ScenarioPhase.running.value
    assert [item["task_kind"] for item in checkpoint["child_runs"]] == ["building", "road"]
    assert checkpoint["child_runs"][0]["run_id"] == "run-building"
    assert checkpoint["child_runs"][0]["phase"] == RunPhase.succeeded.value
    assert checkpoint["child_runs"][1]["run_id"] is None


def test_resume_scenario_run_reuses_completed_child_with_artifact(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", str(tmp_path / "scenarios"))
    agent = _TrackingResumeAgentRunService(tmp_path)
    service = ScenarioRunService(agent_run_service=agent)
    request = _resume_request(tmp_path)
    scenario_id, output_dir = _write_resume_checkpoint(
        request=request,
        scenario_id="scenario-resume-completed",
        child_runs=[
            ScenarioCheckpointChildRun(
                run_id="run-existing-building",
                job_type=JobType.building.value,
                task_kind=TaskKind.building.value,
                task_family="building",
                phase=RunPhase.succeeded.value,
                artifact_path=str(tmp_path / "existing-building.zip"),
            ),
            ScenarioCheckpointChildRun(
                run_id=None,
                job_type=JobType.road.value,
                task_kind=TaskKind.road.value,
                task_family="road",
                phase=RunPhase.queued.value,
            ),
        ],
    )
    (tmp_path / "existing-building.zip").write_bytes(b"zip")

    response = service.resume_scenario_run(scenario_id)

    assert response.phase == ScenarioPhase.succeeded
    assert response.child_run_ids == ["run-existing-building", "run-road"]
    assert [request.job_type for request in agent.create_run_requests] == [JobType.road]
    summary = json.loads((output_dir / "scenario_summary.json").read_text(encoding="utf-8"))
    assert [item["run_id"] for item in summary["child_runs"]] == ["run-existing-building", "run-road"]
    checkpoint = json.loads((output_dir / "scenario_checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["resume_count"] == 1


def test_resume_scenario_run_loads_checkpoint_without_registry_or_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", str(tmp_path / "scenarios"))
    agent = _TrackingResumeAgentRunService(tmp_path)
    service = ScenarioRunService(agent_run_service=agent)
    request = _resume_request(tmp_path)
    scenario_id, output_dir = _write_resume_checkpoint(
        request=request,
        scenario_id="scenario-resume-checkpoint-only",
        child_runs=[
            ScenarioCheckpointChildRun(
                run_id=None,
                job_type=JobType.building.value,
                task_kind=TaskKind.building.value,
                task_family="building",
                phase=RunPhase.queued.value,
            ),
            ScenarioCheckpointChildRun(
                run_id=None,
                job_type=JobType.road.value,
                task_kind=TaskKind.road.value,
                task_family="road",
                phase=RunPhase.queued.value,
            ),
        ],
        record_registry=False,
    )

    response = service.resume_scenario_run(scenario_id)

    assert response.phase == ScenarioPhase.succeeded
    assert response.child_run_ids == ["run-building", "run-road"]
    assert (output_dir / "scenario_summary.json").exists()
    checkpoint = json.loads((output_dir / "scenario_checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["resume_count"] == 1


def test_resume_scenario_run_launches_unstarted_child(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", str(tmp_path / "scenarios"))
    agent = _TrackingResumeAgentRunService(tmp_path)
    service = ScenarioRunService(agent_run_service=agent)
    request = _resume_request(tmp_path)
    scenario_id, _output_dir = _write_resume_checkpoint(
        request=request,
        scenario_id="scenario-resume-unstarted",
        child_runs=[
            ScenarioCheckpointChildRun(
                run_id="run-existing-building",
                job_type=JobType.building.value,
                task_kind=TaskKind.building.value,
                task_family="building",
                phase=RunPhase.succeeded.value,
                artifact_path=str(tmp_path / "existing-building.zip"),
            ),
            ScenarioCheckpointChildRun(
                run_id=None,
                job_type=JobType.road.value,
                task_kind=TaskKind.road.value,
                task_family="road",
                phase=RunPhase.queued.value,
            ),
        ],
    )
    (tmp_path / "existing-building.zip").write_bytes(b"zip")

    response = service.resume_scenario_run(scenario_id)

    assert response.child_run_ids == ["run-existing-building", "run-road"]
    assert agent.created_task_keys == ["road"]


def test_resume_scenario_run_keeps_failed_child_by_default(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", str(tmp_path / "scenarios"))
    agent = _TrackingResumeAgentRunService(tmp_path)
    service = ScenarioRunService(agent_run_service=agent)
    request = _resume_request(tmp_path)
    scenario_id, output_dir = _write_resume_checkpoint(
        request=request,
        scenario_id="scenario-resume-failed-default",
        child_runs=[
            ScenarioCheckpointChildRun(
                run_id="run-existing-building",
                job_type=JobType.building.value,
                task_kind=TaskKind.building.value,
                task_family="building",
                phase=RunPhase.succeeded.value,
                artifact_path=str(tmp_path / "existing-building.zip"),
            ),
            ScenarioCheckpointChildRun(
                run_id="run-failed-road",
                job_type=JobType.road.value,
                task_kind=TaskKind.road.value,
                task_family="road",
                phase=RunPhase.failed.value,
                error="SOURCE_DOWNLOAD_FAILED: timeout",
            ),
        ],
    )
    (tmp_path / "existing-building.zip").write_bytes(b"zip")

    response = service.resume_scenario_run(scenario_id)

    assert response.phase == ScenarioPhase.partial
    assert response.child_run_ids == ["run-existing-building", "run-failed-road"]
    assert agent.created_task_keys == []
    summary = json.loads((output_dir / "scenario_summary.json").read_text(encoding="utf-8"))
    assert summary["child_runs"][1]["phase"] == RunPhase.failed.value


def test_resume_scenario_run_retries_failed_child_when_requested(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", str(tmp_path / "scenarios"))
    agent = _RetryRoadResumeAgentRunService(tmp_path)
    service = ScenarioRunService(agent_run_service=agent)
    request = _resume_request(tmp_path)
    scenario_id, output_dir = _write_resume_checkpoint(
        request=request,
        scenario_id="scenario-resume-failed-retry",
        child_runs=[
            ScenarioCheckpointChildRun(
                run_id="run-existing-building",
                job_type=JobType.building.value,
                task_kind=TaskKind.building.value,
                task_family="building",
                phase=RunPhase.succeeded.value,
                artifact_path=str(tmp_path / "existing-building.zip"),
            ),
            ScenarioCheckpointChildRun(
                run_id="run-failed-road",
                job_type=JobType.road.value,
                task_kind=TaskKind.road.value,
                task_family="road",
                phase=RunPhase.failed.value,
                error="SOURCE_DOWNLOAD_FAILED: timeout",
            ),
        ],
    )
    (tmp_path / "existing-building.zip").write_bytes(b"zip")

    response = service.resume_scenario_run(scenario_id, retry_failed=True)

    assert response.phase == ScenarioPhase.succeeded
    assert response.child_run_ids == ["run-existing-building", "run-retry-road"]
    assert agent.created_task_keys == ["road"]
    summary = json.loads((output_dir / "scenario_summary.json").read_text(encoding="utf-8"))
    assert summary["child_runs"][1]["run_id"] == "run-retry-road"


def test_scenario_run_service_refreshes_child_status_before_summary(tmp_path):
    service = ScenarioRunService(agent_run_service=_QueuedThenSucceededAgentRunService(tmp_path))

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
            disaster_type="flood",
            job_types=[JobType.building],
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    scenario_dir = Path(response.output_dir)
    summary = json.loads((scenario_dir / "scenario_summary.json").read_text(encoding="utf-8"))
    assert response.phase == ScenarioPhase.succeeded
    assert summary["mission"]["scope_source"] == "explicit_job_types"
    assert summary["mission"]["task_kinds"] == ["building"]
    assert summary["mission"]["task_families"] == ["building"]
    assert summary["child_runs"][0]["phase"] == RunPhase.succeeded.value
    assert summary["workflow_traces"][0]["steps"]
    assert summary["final_outputs"]


def test_scenario_run_service_waits_for_async_child_terminal_state_before_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(ScenarioRunService, "CHILD_RUN_POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(ScenarioRunService, "CHILD_RUN_TERMINAL_WAIT_SECONDS", 1)
    service = ScenarioRunService(agent_run_service=_PollingQueuedThenSucceededAgentRunService(tmp_path))

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
            disaster_type="flood",
            job_types=[JobType.building],
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    scenario_dir = Path(response.output_dir)
    summary = json.loads((scenario_dir / "scenario_summary.json").read_text(encoding="utf-8"))
    assert response.phase == ScenarioPhase.succeeded
    assert summary["child_runs"][0]["phase"] == RunPhase.succeeded.value
    assert summary["workflow_traces"][0]["steps"]
    assert summary["final_outputs"]


def test_scenario_run_service_starts_all_children_before_waiting_for_terminal_state(tmp_path, monkeypatch):
    monkeypatch.setattr(ScenarioRunService, "CHILD_RUN_POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(ScenarioRunService, "CHILD_RUN_TERMINAL_WAIT_SECONDS", 1)
    fake = _StartAllChildrenBeforeTerminalAgentRunService(tmp_path)
    service = ScenarioRunService(agent_run_service=fake)

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
            disaster_type="flood",
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    scenario_dir = Path(response.output_dir)
    summary = json.loads((scenario_dir / "scenario_summary.json").read_text(encoding="utf-8"))
    assert response.child_run_ids == [
        "run-building",
        "run-road",
        "run-water-polygon",
        "run-waterways",
        "run-poi",
    ]
    assert response.phase == ScenarioPhase.succeeded
    assert fake.created_job_types == [JobType.building, JobType.road, JobType.water, JobType.water, JobType.poi]
    assert fake.created_task_kinds == [
        "building",
        "road",
        "water_polygon",
        "waterways",
        "poi",
    ]
    assert [item["task_kind"] for item in summary["child_runs"]] == fake.created_task_kinds
    assert [item["task_family"] for item in summary["child_runs"]] == [
        "building",
        "road",
        "water",
        "water",
        "poi",
    ]
    assert summary["mission"]["scope_source"] == "default_disaster_bundle"
    assert summary["mission"]["task_kinds"] == [
        "building",
        "road",
        "water_polygon",
        "waterways",
        "poi",
    ]
    assert summary["mission"]["task_families"] == ["building", "road", "water", "poi"]
    assert [item["phase"] for item in summary["child_runs"]] == [RunPhase.succeeded.value] * 5
    assert [item["task_kind"] for item in summary["source_coverage"]] == fake.created_task_kinds
    assert [item["task_family"] for item in summary["source_coverage"]] == [
        "building",
        "road",
        "water",
        "water",
        "poi",
    ]
    assert [item["task_kind"] for item in summary["evaluation"]["data_fusion_metrics"]] == fake.created_task_kinds
    assert [item["task_family"] for item in summary["evaluation"]["data_fusion_metrics"]] == [
        "building",
        "road",
        "water",
        "water",
        "poi",
    ]
    assert summary["quality"]["accepted_child_count"] == 5
    assert summary["quality"]["rejected_child_count"] == 0
    assert [item["task_kind"] for item in summary["quality"]["child_reports"]] == fake.created_task_kinds
    assert all(item.get("policy_id") for item in summary["quality"]["child_reports"])
    assert all(trace["steps"] for trace in summary["workflow_traces"])


def test_scenario_run_service_can_run_children_concurrently_in_local_eager_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOFUSION_CELERY_EAGER", "1")
    monkeypatch.setenv("GEOFUSION_SCENARIO_CHILD_MAX_WORKERS", "5")
    monkeypatch.setattr(ScenarioRunService, "CHILD_RUN_POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(ScenarioRunService, "CHILD_RUN_TERMINAL_WAIT_SECONDS", 1)
    fake = _BlockingConcurrentAgentRunService(tmp_path, expected_children=5)
    service = ScenarioRunService(agent_run_service=fake)

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
            disaster_type="flood",
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    assert fake.max_simultaneous_create_run_calls == 5
    assert sorted(fake.created_task_kinds) == ["building", "poi", "road", "water_polygon", "waterways"]
    assert response.child_run_ids == [
        "run-building",
        "run-road",
        "run-water-polygon",
        "run-waterways",
        "run-poi",
    ]
    assert response.phase == ScenarioPhase.succeeded


def test_scenario_run_service_uses_isolated_runtime_dependencies_for_concurrent_children(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOFUSION_SCENARIO_CHILD_MAX_WORKERS", "5")
    monkeypatch.setattr(ScenarioRunService, "CHILD_RUN_POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(ScenarioRunService, "CHILD_RUN_TERMINAL_WAIT_SECONDS", 1)
    fake = _RuntimeDependencyAwareConcurrentAgentRunService(tmp_path, expected_children=5)
    service = ScenarioRunService(agent_run_service=fake)

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
            disaster_type="flood",
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    assert response.phase == ScenarioPhase.succeeded
    assert all(runtime_id is not None for runtime_id in fake.create_run_runtime_dependency_ids)
    assert len(set(fake.create_run_runtime_dependency_ids)) == 5


def test_scenario_run_service_does_not_build_object_runtimes_for_non_eager_children(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOFUSION_SCENARIO_CHILD_MAX_WORKERS", "5")
    monkeypatch.setattr(ScenarioRunService, "CHILD_RUN_POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(ScenarioRunService, "CHILD_RUN_TERMINAL_WAIT_SECONDS", 1)
    fake = _RuntimeDependencyAwareConcurrentAgentRunService(tmp_path, expected_children=5)
    fake.dispatch_eager = False
    service = ScenarioRunService(agent_run_service=fake)

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
            disaster_type="flood",
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    assert response.phase == ScenarioPhase.succeeded
    assert fake.build_isolated_runtime_dependencies_calls == 0
    assert fake.create_run_runtime_dependency_ids == [None] * 5


def test_scenario_run_service_refresh_preserves_result_with_invalid_task_kind(tmp_path):
    service = ScenarioRunService(agent_run_service=_FakeAgentRunService(tmp_path))
    result = {
        "run_id": "run-water",
        "job_type": JobType.water.value,
        "task_kind": "not_a_task_kind",
        "task_family": "water",
        "phase": RunPhase.queued.value,
    }

    refreshed = service._refresh_started_child_result(result)

    assert refreshed == result


def test_scenario_run_service_uses_one_global_child_wait_deadline(tmp_path, monkeypatch):
    monkeypatch.setattr(ScenarioRunService, "CHILD_RUN_POLL_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(ScenarioRunService, "CHILD_RUN_TERMINAL_WAIT_SECONDS", 0)
    service = ScenarioRunService(agent_run_service=_NeverTerminalAgentRunService(tmp_path))

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
            disaster_type="flood",
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    scenario_dir = Path(response.output_dir)
    summary = json.loads((scenario_dir / "scenario_summary.json").read_text(encoding="utf-8"))
    assert response.child_run_ids == [
        "run-building",
        "run-road",
        "run-water-polygon",
        "run-waterways",
        "run-poi",
    ]
    assert response.phase == ScenarioPhase.running
    assert [item["phase"] for item in summary["child_runs"]] == [RunPhase.queued.value] * 5


def test_scenario_run_service_marks_succeeded_degraded_child_as_partial(tmp_path):
    service = ScenarioRunService(agent_run_service=_DegradedSucceededAgentRunService(tmp_path))

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood road",
            trigger_content="run road fusion for Karachi flood",
            disaster_type="flood",
            job_types=[JobType.road],
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    scenario_dir = Path(response.output_dir)
    summary = json.loads((scenario_dir / "scenario_summary.json").read_text(encoding="utf-8"))
    assert response.phase == ScenarioPhase.partial
    assert summary["phase"] == ScenarioPhase.partial.value
    assert summary["child_runs"][0]["phase"] == RunPhase.succeeded.value
    assert summary["child_runs"][0]["degradation"]["state"] == "degraded"


def test_scenario_run_service_keeps_all_failed_children_failed_even_with_degraded_evidence(tmp_path):
    service = ScenarioRunService(agent_run_service=_FailedDegradedAgentRunService(tmp_path))

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood road",
            trigger_content="run road fusion for Karachi flood",
            disaster_type="flood",
            job_types=[JobType.road],
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    assert response.phase == ScenarioPhase.failed


def test_partial_scenario_records_failed_child_recovery_state(tmp_path, monkeypatch):
    monkeypatch.setattr(ScenarioRunService, "CHILD_RUN_POLL_INTERVAL_SECONDS", 0)
    service = ScenarioRunService(agent_run_service=_OneSucceededOneFailedAgentRunService(tmp_path))

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请执行地理空间矢量数据融合。",
            disaster_type="flood",
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    summary = json.loads((Path(response.output_dir) / "scenario_summary.json").read_text(encoding="utf-8"))

    assert response.phase == ScenarioPhase.partial
    assert summary["failed_children"]
    assert summary["failed_children"][0]["recovery_state"] in {"retry_scheduled", "blocked", "exhausted"}
    assert (Path(response.output_dir) / "failed_children.json").exists()
    assert summary["final_outputs"]


def test_scenario_run_service_checkpoint_records_failed_child_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(ScenarioRunService, "CHILD_RUN_POLL_INTERVAL_SECONDS", 0)
    service = ScenarioRunService(agent_run_service=_OneSucceededOneFailedAgentRunService(tmp_path))

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请执行地理空间矢量数据融合。",
            disaster_type="flood",
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    checkpoint = json.loads((Path(response.output_dir) / "scenario_checkpoint.json").read_text(encoding="utf-8"))

    assert response.phase == ScenarioPhase.partial
    failed_runs = [item for item in checkpoint["child_runs"] if item["phase"] == RunPhase.failed.value]
    assert [item["task_kind"] for item in failed_runs] == ["poi"]
    assert failed_runs[0]["error"] == "SOURCE_DOWNLOAD_FAILED: timeout"


def test_scenario_checkpoint_service_atomic_write_and_load_round_trip(tmp_path):
    from schemas.scenario_checkpoint import ScenarioCheckpoint
    from services.scenario_checkpoint_service import (
        checkpoint_path,
        load_scenario_checkpoint,
        write_scenario_checkpoint,
    )

    path = checkpoint_path(tmp_path)
    checkpoint = ScenarioCheckpoint(
        scenario_id="scenario-test",
        phase=ScenarioPhase.running,
        request={"scenario_name": "Karachi flood", "trigger_content": "run scenario"},
        child_specs=[],
        child_runs=[],
        started_at="2026-06-05T00:00:00+00:00",
        updated_at="2026-06-05T00:00:01+00:00",
    )

    write_scenario_checkpoint(path, checkpoint)
    loaded = load_scenario_checkpoint(path)

    assert path == tmp_path / "scenario_checkpoint.json"
    assert loaded == checkpoint
    assert not (tmp_path / "scenario_checkpoint.json.tmp").exists()


def test_scenario_checkpoint_atomic_write_keeps_old_file_when_replace_fails(tmp_path, monkeypatch):
    from schemas.scenario_checkpoint import ScenarioCheckpoint
    from services.scenario_checkpoint_service import (
        checkpoint_path,
        load_scenario_checkpoint,
        write_scenario_checkpoint,
    )

    path = checkpoint_path(tmp_path)
    old_checkpoint = ScenarioCheckpoint(
        scenario_id="scenario-old",
        phase=ScenarioPhase.running,
        request={"scenario_name": "old", "trigger_content": "old"},
        child_specs=[],
        child_runs=[],
        started_at="2026-06-05T00:00:00+00:00",
        updated_at="2026-06-05T00:00:01+00:00",
    )
    new_checkpoint = old_checkpoint.model_copy(
        update={
            "scenario_id": "scenario-new",
            "request": {"scenario_name": "new", "trigger_content": "new"},
        }
    )
    write_scenario_checkpoint(path, old_checkpoint)

    def fail_replace(self, target):
        raise OSError("replace failed")

    monkeypatch.setattr(type(path), "replace", fail_replace)

    with pytest.raises(OSError, match="replace failed"):
        write_scenario_checkpoint(path, new_checkpoint)

    assert load_scenario_checkpoint(path) == old_checkpoint


def test_scenario_run_service_submit_returns_running_before_background_execution(tmp_path, monkeypatch):
    service = ScenarioRunService(agent_run_service=_FakeAgentRunService(tmp_path))
    submitted = Event()
    captured: dict[str, object] = {}

    def fake_execute(*, request, scenario_id, output_dir):
        captured["scenario_id"] = scenario_id
        captured["output_dir"] = output_dir
        submitted.set()

    monkeypatch.setattr(service, "_execute_scenario_run", fake_execute)

    response = service.submit_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
            disaster_type="flood",
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    assert response.phase == ScenarioPhase.running
    assert response.child_run_ids == []
    scenario_dir = Path(response.output_dir)
    summary = json.loads((scenario_dir / "scenario_summary.json").read_text(encoding="utf-8"))
    assert summary["phase"] == ScenarioPhase.running.value
    assert summary["child_runs"] == []
    assert submitted.wait(timeout=2)
    assert captured["scenario_id"] == response.scenario_id


def test_scenario_run_service_submit_writes_initial_checkpoint(tmp_path, monkeypatch):
    service = ScenarioRunService(agent_run_service=_FakeAgentRunService(tmp_path))

    def fake_execute(*, request, scenario_id, output_dir):
        return None

    monkeypatch.setattr(service, "_execute_scenario_run", fake_execute)

    response = service.submit_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
            disaster_type="flood",
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    checkpoint = json.loads((Path(response.output_dir) / "scenario_checkpoint.json").read_text(encoding="utf-8"))

    assert checkpoint["scenario_id"] == response.scenario_id
    assert checkpoint["phase"] == ScenarioPhase.running.value
    assert checkpoint["request"]["scenario_name"] == "Karachi flood"
    assert checkpoint["child_specs"] == []
    assert checkpoint["child_runs"] == []
    assert checkpoint["resume_count"] == 0


def _write_quality_report(artifact: Path, *, run_id: str, task_key: str) -> None:
    quality_report = {
        "task_kind": task_key.replace("-", "_"),
        "accepted": True,
        "failure_reasons": [],
        "policy_id": f"quality.default.{task_key.replace('-', '_')}.v1",
    }
    (artifact.parent / f"{run_id}_quality_report.json").write_text(
        json.dumps(quality_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _resume_request(tmp_path: Path) -> ScenarioRunRequest:
    return ScenarioRunRequest(
        scenario_name="Parakou earthquake",
        trigger_content="fuse building and road data for Parakou, Benin after an earthquake",
        disaster_type="earthquake",
        job_types=[JobType.building, JobType.road],
        output_root=str(tmp_path / "scenarios"),
    )


def _write_resume_checkpoint(
    *,
    request: ScenarioRunRequest,
    scenario_id: str,
    child_runs: list[ScenarioCheckpointChildRun],
    record_registry: bool = True,
) -> tuple[str, Path]:
    output_dir = Path(request.output_root or "") / scenario_id
    output_dir.mkdir(parents=True, exist_ok=True)
    child_specs = build_child_run_specs(request)
    checkpoint = ScenarioCheckpoint(
        scenario_id=scenario_id,
        phase=ScenarioPhase.running,
        children_phase=ScenarioPhase.running,
        request=request.model_dump(mode="json"),
        child_specs=[
            {
                "job_type": spec.job_type.value,
                "trigger_content": spec.trigger_content,
                "disaster_type": spec.disaster_type,
                "spatial_extent": spec.spatial_extent,
                "force_aoi_resolution": spec.force_aoi_resolution,
                "target_crs": spec.target_crs,
                "debug": spec.debug,
                "task_kind": spec.task_kind.value if spec.task_kind else None,
                "task_family": spec.task_family,
                "preferred_pattern_id": spec.preferred_pattern_id,
                "output_data_type": spec.output_data_type,
            }
            for spec in child_specs
        ],
        child_runs=child_runs,
        started_at="2026-06-05T00:00:00+00:00",
        updated_at="2026-06-05T00:00:01+00:00",
    )
    write_scenario_checkpoint(checkpoint_path(output_dir), checkpoint)
    if record_registry:
        ScenarioRegistryService(output_root=Path(request.output_root or "")).record(
            {
                "scenario_id": scenario_id,
                "scenario_name": request.scenario_name,
                "phase": ScenarioPhase.running.value,
                "output_dir": str(output_dir),
                "child_run_ids": [run.run_id for run in child_runs if run.run_id],
                "created_at": "2026-06-05T00:00:00+00:00",
            }
        )
    return scenario_id, output_dir


class _FakeAgentRunService:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.statuses: dict[str, RunStatus] = {}
        self.plans: dict[str, WorkflowPlan] = {}
        self.events: dict[str, list[RunEvent]] = {}
        self.artifacts: dict[str, Path] = {}

    def create_run(self, *, request, osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes):
        task_key = _task_key_from_request(request)
        run_id = f"run-{task_key}"
        status = RunStatus(
            run_id=run_id,
            job_type=request.job_type,
            trigger=request.trigger,
            phase=RunPhase.succeeded,
            progress=100,
            target_crs=request.target_crs or "EPSG:32631",
            debug=False,
            created_at="2026-04-21T00:00:00+00:00",
            finished_at="2026-04-21T00:00:01+00:00",
        )
        self.statuses[run_id] = status
        self.plans[run_id] = _make_plan(request.job_type)
        self.events[run_id] = _make_events(request.job_type)
        artifact = self.tmp_path / f"{run_id}.zip"
        artifact.write_bytes(b"zip")
        _write_quality_report(artifact, run_id=run_id, task_key=task_key)
        self.artifacts[run_id] = artifact
        return status

    def get_plan(self, run_id: str):
        return self.plans.get(run_id)

    def get_audit_events(self, run_id: str):
        return list(self.events.get(run_id, []))

    def get_artifact_path(self, run_id: str):
        return self.artifacts.get(run_id)


class _TrackingResumeAgentRunService(_FakeAgentRunService):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(tmp_path)
        self.create_run_requests = []
        self.created_task_keys: list[str] = []

    def create_run(self, *, request, osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes):
        self.create_run_requests.append(request)
        self.created_task_keys.append(_task_key_from_request(request))
        return super().create_run(
            request=request,
            osm_zip_name=osm_zip_name,
            osm_zip_bytes=osm_zip_bytes,
            ref_zip_name=ref_zip_name,
            ref_zip_bytes=ref_zip_bytes,
        )

    def get_run(self, run_id: str):
        return self.statuses.get(run_id)


class _RetryRoadResumeAgentRunService(_TrackingResumeAgentRunService):
    def create_run(self, *, request, osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes):
        if _task_key_from_request(request) != "road":
            return super().create_run(
                request=request,
                osm_zip_name=osm_zip_name,
                osm_zip_bytes=osm_zip_bytes,
                ref_zip_name=ref_zip_name,
                ref_zip_bytes=ref_zip_bytes,
            )
        self.create_run_requests.append(request)
        self.created_task_keys.append("road")
        run_id = "run-retry-road"
        status = RunStatus(
            run_id=run_id,
            job_type=request.job_type,
            trigger=request.trigger,
            phase=RunPhase.succeeded,
            progress=100,
            target_crs=request.target_crs or "EPSG:32631",
            debug=False,
            created_at="2026-04-21T00:00:00+00:00",
            finished_at="2026-04-21T00:00:01+00:00",
        )
        self.statuses[run_id] = status
        self.plans[run_id] = _make_plan(request.job_type)
        self.events[run_id] = _make_events(request.job_type)
        artifact = self.tmp_path / f"{run_id}.zip"
        artifact.write_bytes(b"zip")
        _write_quality_report(artifact, run_id=run_id, task_key="road")
        self.artifacts[run_id] = artifact
        return status


class _QueuedThenSucceededAgentRunService(_FakeAgentRunService):
    def create_run(self, *, request, osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes):
        task_key = _task_key_from_request(request)
        run_id = f"run-{task_key}"
        queued = RunStatus(
            run_id=run_id,
            job_type=request.job_type,
            trigger=request.trigger,
            phase=RunPhase.queued,
            progress=0,
            target_crs=request.target_crs or "EPSG:32631",
            debug=False,
            created_at="2026-04-21T00:00:00+00:00",
        )
        succeeded = queued.model_copy(
            update={
                "phase": RunPhase.succeeded,
                "progress": 100,
                "finished_at": "2026-04-21T00:00:03+00:00",
            }
        )
        self.statuses[run_id] = succeeded
        self.plans[run_id] = _make_plan(request.job_type)
        self.events[run_id] = _make_events(request.job_type)
        artifact = self.tmp_path / f"{run_id}.zip"
        artifact.write_bytes(b"zip")
        _write_quality_report(artifact, run_id=run_id, task_key=task_key)
        self.artifacts[run_id] = artifact
        return queued

    def get_run(self, run_id: str):
        return self.statuses.get(run_id)


class _InterruptAfterFirstChildAgentRunService(_FakeAgentRunService):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(tmp_path)
        self.create_run_calls = 0

    def create_run(self, *, request, osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes):
        self.create_run_calls += 1
        if self.create_run_calls == 2:
            raise KeyboardInterrupt("process interrupted")
        return super().create_run(
            request=request,
            osm_zip_name=osm_zip_name,
            osm_zip_bytes=osm_zip_bytes,
            ref_zip_name=ref_zip_name,
            ref_zip_bytes=ref_zip_bytes,
        )


class _PollingQueuedThenSucceededAgentRunService(_FakeAgentRunService):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(tmp_path)
        self.get_run_calls: dict[str, int] = {}

    def create_run(self, *, request, osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes):
        task_key = _task_key_from_request(request)
        run_id = f"run-{task_key}"
        queued = RunStatus(
            run_id=run_id,
            job_type=request.job_type,
            trigger=request.trigger,
            phase=RunPhase.queued,
            progress=0,
            target_crs=request.target_crs or "EPSG:32631",
            debug=False,
            created_at="2026-04-21T00:00:00+00:00",
        )
        succeeded = queued.model_copy(
            update={
                "phase": RunPhase.succeeded,
                "progress": 100,
                "finished_at": "2026-04-21T00:00:03+00:00",
            }
        )
        self.statuses[run_id] = succeeded
        self.plans[run_id] = _make_plan(request.job_type)
        self.events[run_id] = _make_events(request.job_type)
        artifact = self.tmp_path / f"{run_id}.zip"
        artifact.write_bytes(b"zip")
        _write_quality_report(artifact, run_id=run_id, task_key=task_key)
        self.artifacts[run_id] = artifact
        return queued

    def get_run(self, run_id: str):
        count = self.get_run_calls.get(run_id, 0) + 1
        self.get_run_calls[run_id] = count
        if count == 1:
            return self.statuses[run_id].model_copy(update={"phase": RunPhase.queued, "progress": 0})
        return self.statuses.get(run_id)


class _StartAllChildrenBeforeTerminalAgentRunService(_FakeAgentRunService):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(tmp_path)
        self.created_job_types: list[JobType] = []
        self.created_task_kinds: list[str] = []

    def create_run(self, *, request, osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes):
        self.created_job_types.append(request.job_type)
        task_key = _task_key_from_request(request)
        self.created_task_kinds.append(task_key.replace("-", "_"))
        run_id = f"run-{task_key}"
        queued = RunStatus(
            run_id=run_id,
            job_type=request.job_type,
            trigger=request.trigger,
            phase=RunPhase.queued,
            progress=0,
            target_crs=request.target_crs or "EPSG:32631",
            debug=False,
            created_at="2026-04-21T00:00:00+00:00",
        )
        self.statuses[run_id] = queued
        self.plans[run_id] = _make_plan(request.job_type)
        self.events[run_id] = _make_events(request.job_type)
        artifact = self.tmp_path / f"{run_id}.zip"
        artifact.write_bytes(b"zip")
        _write_quality_report(artifact, run_id=run_id, task_key=task_key)
        self.artifacts[run_id] = artifact
        return queued

    def get_run(self, run_id: str):
        if len(self.created_job_types) < 5:
            return self.statuses[run_id]
        succeeded = self.statuses[run_id].model_copy(
            update={
                "phase": RunPhase.succeeded,
                "progress": 100,
                "finished_at": "2026-04-21T00:00:03+00:00",
            }
        )
        self.statuses[run_id] = succeeded
        return succeeded


class _BlockingConcurrentAgentRunService(_FakeAgentRunService):
    def __init__(self, tmp_path: Path, *, expected_children: int) -> None:
        super().__init__(tmp_path)
        self.expected_children = expected_children
        self.created_task_kinds: list[str] = []
        self.max_simultaneous_create_run_calls = 0
        self._active_create_run_calls = 0
        self._entered_create_run_calls = 0
        self._lock = Lock()
        self._all_children_entered = Event()

    def create_run(self, *, request, osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes):
        task_key = _task_key_from_request(request)
        with self._lock:
            self.created_task_kinds.append(task_key.replace("-", "_"))
            self._active_create_run_calls += 1
            self._entered_create_run_calls += 1
            self.max_simultaneous_create_run_calls = max(
                self.max_simultaneous_create_run_calls,
                self._active_create_run_calls,
            )
            if self._entered_create_run_calls == self.expected_children:
                self._all_children_entered.set()

        try:
            if not self._all_children_entered.wait(timeout=5):
                raise RuntimeError("not all child create_run calls entered concurrently")
            return super().create_run(
                request=request,
                osm_zip_name=osm_zip_name,
                osm_zip_bytes=osm_zip_bytes,
                ref_zip_name=ref_zip_name,
                ref_zip_bytes=ref_zip_bytes,
            )
        finally:
            with self._lock:
                self._active_create_run_calls -= 1


class _RuntimeDependencyAwareConcurrentAgentRunService(_BlockingConcurrentAgentRunService):
    def __init__(self, tmp_path: Path, *, expected_children: int) -> None:
        super().__init__(tmp_path, expected_children=expected_children)
        self._runtime_dependency_index = 0
        self.build_isolated_runtime_dependencies_calls = 0
        self.create_run_runtime_dependency_ids: list[int | None] = []

    def build_isolated_runtime_dependencies(self):
        self.build_isolated_runtime_dependencies_calls += 1
        self._runtime_dependency_index += 1
        return object()

    def create_run(
        self,
        *,
        request,
        osm_zip_name,
        osm_zip_bytes,
        ref_zip_name,
        ref_zip_bytes,
        runtime_dependencies=None,
    ):
        self.create_run_runtime_dependency_ids.append(id(runtime_dependencies) if runtime_dependencies is not None else None)
        return super().create_run(
            request=request,
            osm_zip_name=osm_zip_name,
            osm_zip_bytes=osm_zip_bytes,
            ref_zip_name=ref_zip_name,
            ref_zip_bytes=ref_zip_bytes,
        )


class _NeverTerminalAgentRunService(_FakeAgentRunService):
    def create_run(self, *, request, osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes):
        task_key = _task_key_from_request(request)
        run_id = f"run-{task_key}"
        queued = RunStatus(
            run_id=run_id,
            job_type=request.job_type,
            trigger=request.trigger,
            phase=RunPhase.queued,
            progress=0,
            target_crs=request.target_crs or "EPSG:32631",
            debug=False,
            created_at="2026-04-21T00:00:00+00:00",
        )
        self.statuses[run_id] = queued
        self.plans[run_id] = _make_plan(request.job_type)
        self.events[run_id] = []
        return queued

    def get_run(self, run_id: str):
        return self.statuses.get(run_id)


class _DegradedSucceededAgentRunService(_FakeAgentRunService):
    def get_run(self, run_id: str):
        return self.statuses.get(run_id)

    def get_audit_events(self, run_id: str):
        return [
            RunEvent(
                timestamp="2026-06-03T00:00:01+00:00",
                kind="task_inputs_resolved",
                phase=RunPhase.running,
                message="degraded road inputs",
                details={
                    "source_id": "catalog.flood.road",
                    "selected_source_id": "catalog.flood.road",
                    "component_coverage": {
                        "raw.osm.road": {"feature_count": 3, "coverage_status": "available"},
                        "raw.microsoft.road": {"feature_count": 0, "coverage_status": "empty"},
                    },
                },
            ),
            RunEvent(
                timestamp="2026-06-03T00:00:02+00:00",
                kind="run_succeeded",
                phase=RunPhase.succeeded,
                message="succeeded with degraded evidence",
            ),
        ]


class _FailedDegradedAgentRunService(_DegradedSucceededAgentRunService):
    def create_run(self, *, request, osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes):
        status = super().create_run(
            request=request,
            osm_zip_name=osm_zip_name,
            osm_zip_bytes=osm_zip_bytes,
            ref_zip_name=ref_zip_name,
            ref_zip_bytes=ref_zip_bytes,
        )
        failed = status.model_copy(
            update={
                "phase": RunPhase.failed,
                "error": "SOURCE_MISSING: reference unavailable",
                "finished_at": "2026-06-03T00:00:03+00:00",
            }
        )
        self.statuses[status.run_id] = failed
        return failed


class _OneSucceededOneFailedAgentRunService(_FakeAgentRunService):
    def create_run(self, *, request, osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes):
        status = super().create_run(
            request=request,
            osm_zip_name=osm_zip_name,
            osm_zip_bytes=osm_zip_bytes,
            ref_zip_name=ref_zip_name,
            ref_zip_bytes=ref_zip_bytes,
        )
        task_key = _task_key_from_request(request)
        if task_key != "poi":
            return status
        failed = status.model_copy(
            update={
                "phase": RunPhase.failed,
                "progress": 80,
                "error": "SOURCE_DOWNLOAD_FAILED: timeout",
                "failure_summary": "SOURCE_DOWNLOAD_FAILED: timeout",
                "finished_at": "2026-06-03T00:00:03+00:00",
            }
        )
        self.statuses[status.run_id] = failed
        self.artifacts.pop(status.run_id, None)
        return failed


def _task_key_from_request(request) -> str:
    preferred = str(getattr(request, "preferred_pattern_id", "") or "")
    if preferred == "wp.flood.water_polygon.default":
        return "water-polygon"
    if preferred == "wp.flood.waterways.default":
        return "waterways"
    return request.job_type.value


def _make_plan(job_type: JobType) -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id=f"wf-{job_type.value}",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="Parakou"),
        context={
            "retrieval": {
                "candidate_patterns": [{"pattern_id": f"wp.earthquake.{job_type.value}", "success_rate": 0.9}],
                "data_sources": [{"source_id": f"catalog.earthquake.{job_type.value}"}],
            },
            "plan_revision": 1,
        },
        tasks=[
            WorkflowTask(
                step=1,
                name=f"{job_type.value}_fusion",
                description="fusion",
                algorithm_id=f"algo.fusion.{job_type.value}.v1",
                input=WorkflowTaskInput(
                    data_type_id=f"dt.{job_type.value}.bundle",
                    data_source_id=f"catalog.earthquake.{job_type.value}",
                ),
                output=WorkflowTaskOutput(data_type_id=f"dt.{job_type.value}.fused"),
                kg_validated=True,
            )
        ],
        expected_output=f"{job_type.value} fused",
        validation=ValidationReport(valid=True),
    )


def _make_events(job_type: JobType) -> list[RunEvent]:
    return [
        RunEvent(
            timestamp="2026-04-21T00:00:00+00:00",
            kind="plan_created",
            phase=RunPhase.validating,
            message="plan",
            details={"selected_pattern": f"wp.earthquake.{job_type.value}"},
        ),
        RunEvent(
            timestamp="2026-04-21T00:00:01+00:00",
            kind="task_inputs_resolved",
            phase=RunPhase.running,
            message="inputs",
            details={
                "source_id": f"catalog.earthquake.{job_type.value}",
                "selected_source_id": f"catalog.earthquake.{job_type.value}",
                "component_coverage": {},
            },
        ),
        RunEvent(
            timestamp="2026-04-21T00:00:02+00:00",
            kind="durable_learning_recorded",
            phase=RunPhase.running,
            message="learning",
        ),
        RunEvent(
            timestamp="2026-04-21T00:00:03+00:00",
            kind="run_succeeded",
            phase=RunPhase.succeeded,
            message="succeeded",
        ),
    ]
