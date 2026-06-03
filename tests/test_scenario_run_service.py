from __future__ import annotations

import json
from pathlib import Path
from threading import Event

from schemas.agent import RunEvent, RunPhase, RunStatus, RunTrigger, RunTriggerType, ValidationReport, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from schemas.fusion import JobType
from schemas.scenario import ScenarioPhase, ScenarioRunRequest
from schemas.task_kind import TaskKind
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
    assert (scenario_dir / "documents" / "scenario_report.zh.md").exists()
    assert (scenario_dir / "documents" / "scenario_report.en.md").exists()


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
    assert [item["phase"] for item in summary["child_runs"]] == [RunPhase.succeeded.value] * 5
    assert all(trace["steps"] for trace in summary["workflow_traces"])


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
        self.artifacts[run_id] = artifact
        return status

    def get_plan(self, run_id: str):
        return self.plans.get(run_id)

    def get_audit_events(self, run_id: str):
        return list(self.events.get(run_id, []))

    def get_artifact_path(self, run_id: str):
        return self.artifacts.get(run_id)


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
        self.artifacts[run_id] = artifact
        return queued

    def get_run(self, run_id: str):
        return self.statuses.get(run_id)


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
                        "raw.overture.transportation": {"feature_count": 0, "coverage_status": "empty"},
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
