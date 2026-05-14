from __future__ import annotations

import json
from pathlib import Path

from schemas.agent import RunEvent, RunPhase, RunStatus, RunTrigger, RunTriggerType, ValidationReport, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from schemas.fusion import JobType
from schemas.scenario import ScenarioPhase, ScenarioRunRequest
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


class _FakeAgentRunService:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.statuses: dict[str, RunStatus] = {}
        self.plans: dict[str, WorkflowPlan] = {}
        self.events: dict[str, list[RunEvent]] = {}
        self.artifacts: dict[str, Path] = {}

    def create_run(self, *, request, osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes):
        run_id = f"run-{request.job_type.value}"
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
