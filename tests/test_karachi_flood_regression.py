from __future__ import annotations

from pathlib import Path

from schemas.agent import (
    RunEvent,
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
from schemas.scenario import ScenarioRunRequest
from services.scenario_run_service import ScenarioRunService


def test_karachi_chinese_flood_scenario_expands_and_records_finished_children(tmp_path: Path) -> None:
    service = ScenarioRunService(agent_run_service=_KarachiFakeAgentRunService(tmp_path))

    response = service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Karachi flood",
            trigger_content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
            disaster_type="flood",
            spatial_extent="Karachi, Pakistan",
            output_root=str(tmp_path / "scenarios"),
        )
    )

    assert response.phase.value == "succeeded"
    assert response.child_run_ids == [
        "run-building",
        "run-road",
        "run-water-polygon",
        "run-waterways",
        "run-poi",
    ]
    summary_path = Path(response.output_dir) / "scenario_summary.json"
    assert summary_path.exists()
    summary_text = summary_path.read_text(encoding="utf-8")
    assert "run-building" in summary_text
    assert "run-road" in summary_text
    assert "run-water-polygon" in summary_text
    assert "run-waterways" in summary_text
    assert "run-poi" in summary_text


class _KarachiFakeAgentRunService:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.statuses: dict[str, RunStatus] = {}
        self.plans: dict[str, WorkflowPlan] = {}
        self.events: dict[str, list[RunEvent]] = {}
        self.artifacts: dict[str, Path] = {}

    def create_run(self, *, request, osm_zip_name, osm_zip_bytes, ref_zip_name, ref_zip_bytes):
        task_key = _task_key(request)
        run_id = f"run-{task_key}"
        status = RunStatus(
            run_id=run_id,
            job_type=request.job_type,
            trigger=request.trigger,
            phase=RunPhase.succeeded,
            progress=100,
            target_crs=request.target_crs or "EPSG:32643",
            debug=False,
            created_at="2026-06-01T00:00:00+00:00",
            finished_at="2026-06-01T00:00:03+00:00",
        )
        self.statuses[run_id] = status
        self.plans[run_id] = _make_plan(request)
        self.events[run_id] = _make_events(request)
        artifact = self.tmp_path / f"{run_id}.zip"
        artifact.write_bytes(b"zip")
        self.artifacts[run_id] = artifact
        return status

    def get_run(self, run_id: str):
        return self.statuses.get(run_id)

    def get_plan(self, run_id: str):
        return self.plans.get(run_id)

    def get_audit_events(self, run_id: str):
        return list(self.events.get(run_id, []))

    def get_artifact_path(self, run_id: str):
        return self.artifacts.get(run_id)


def _task_key(request) -> str:
    preferred = str(getattr(request, "preferred_pattern_id", "") or "")
    if preferred == "wp.flood.water_polygon.default":
        return "water-polygon"
    if preferred == "wp.flood.waterways.default":
        return "waterways"
    return request.job_type.value


def _source_id(request) -> str:
    preferred = str(getattr(request, "preferred_pattern_id", "") or "")
    if preferred == "wp.flood.water_polygon.default":
        return "catalog.flood.water_polygon"
    if preferred == "wp.flood.waterways.default":
        return "catalog.flood.waterways"
    return f"catalog.flood.{request.job_type.value}"


def _make_plan(request) -> WorkflowPlan:
    job_type = request.job_type
    source_id = _source_id(request)
    return WorkflowPlan(
        workflow_id=f"wf-karachi-{job_type.value}",
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content="巴基斯坦卡拉奇市发生洪涝灾害，请作为灾害响应场景执行地理空间矢量数据融合。",
            disaster_type="flood",
            spatial_extent="Karachi, Pakistan",
        ),
        context={
            "intent": {
                "resolved_aoi": {
                    "display_name": "Karachi Division, Sindh, Pakistan",
                    "country_code": "pk",
                    "bbox": [66.2862312, 24.4273517, 67.5827753, 25.676796],
                }
            },
            "retrieval": {
                "candidate_patterns": [{"pattern_id": f"wp.flood.{job_type.value}", "success_rate": 0.9}],
                "data_sources": [{"source_id": source_id}],
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
                    data_source_id=source_id,
                ),
                output=WorkflowTaskOutput(data_type_id=f"dt.{job_type.value}.fused"),
                kg_validated=True,
            )
        ],
        expected_output=f"{job_type.value} fused",
        validation=ValidationReport(valid=True),
    )


def _make_events(request) -> list[RunEvent]:
    source_id = _source_id(request)
    return [
        RunEvent(
            timestamp="2026-06-01T00:00:00+00:00",
            kind="aoi_resolved",
            phase=RunPhase.planning,
            message="aoi",
            details={
                "query": "Karachi, Pakistan",
                "country_code": "pk",
                "bbox": [66.2862312, 24.4273517, 67.5827753, 25.676796],
            },
        ),
        RunEvent(
            timestamp="2026-06-01T00:00:01+00:00",
            kind="task_inputs_resolved",
            phase=RunPhase.running,
            message="inputs",
            details={
                "source_id": source_id,
                "selected_source_id": source_id,
                "component_coverage": {},
            },
        ),
        RunEvent(
            timestamp="2026-06-01T00:00:02+00:00",
            kind="run_succeeded",
            phase=RunPhase.succeeded,
            message="succeeded",
        ),
    ]
