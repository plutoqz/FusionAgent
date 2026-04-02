from __future__ import annotations

import importlib
import json
import sys
import zipfile
from pathlib import Path

from schemas.agent import RunArtifactMeta, RunCreateRequest, RunTrigger, RunTriggerType, WorkflowPlan
from schemas.fusion import JobType


def _write_dummy_zip(path: Path) -> bytes:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("dummy.shp", b"shp")
        zf.writestr("dummy.shx", b"shx")
        zf.writestr("dummy.dbf", b"dbf")
    return path.read_bytes()


def test_worker_celery_app_imports_without_celery_dependency(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, "worker.celery_app", raising=False)
    module = importlib.import_module("worker.celery_app")

    assert hasattr(module, "celery_app")
    assert hasattr(module.celery_app, "task")


def test_scheduled_tick_creates_runs_from_config(tmp_path: Path, monkeypatch) -> None:
    osm_zip = tmp_path / "scheduled_osm.zip"
    ref_zip = tmp_path / "scheduled_ref.zip"
    _write_dummy_zip(osm_zip)
    _write_dummy_zip(ref_zip)

    scheduled_runs = [
        {
            "job_type": "building",
            "trigger_content": "nightly building refresh",
            "disaster_type": "flood",
            "osm_zip_path": str(osm_zip),
            "ref_zip_path": str(ref_zip),
            "target_crs": "EPSG:32643",
        }
    ]
    monkeypatch.setenv("GEOFUSION_SCHEDULED_RUNS", json.dumps(scheduled_runs))

    worker_tasks = importlib.import_module("worker.tasks")
    service_module = importlib.import_module("services.agent_run_service")

    calls: list[RunCreateRequest] = []

    class StubService:
        def create_run(
            self,
            request: RunCreateRequest,
            osm_zip_name: str,
            osm_zip_bytes: bytes,
            ref_zip_name: str,
            ref_zip_bytes: bytes,
        ):
            calls.append(request)
            assert osm_zip_name == "scheduled_osm.zip"
            assert ref_zip_name == "scheduled_ref.zip"
            assert osm_zip_bytes
            assert ref_zip_bytes
            return type("CreatedRun", (), {"run_id": "run-scheduled"})()

    monkeypatch.setattr(service_module, "agent_run_service", StubService())

    result = worker_tasks.scheduled_tick()

    assert result["created"] == 1
    assert result["run_ids"] == ["run-scheduled"]
    assert calls[0].trigger.type == RunTriggerType.scheduled
    assert calls[0].job_type == JobType.building


def test_stage_tasks_delegate_to_agent_run_service(monkeypatch, tmp_path: Path) -> None:
    worker_tasks = importlib.import_module("worker.tasks")
    service_module = importlib.import_module("services.agent_run_service")

    run_request = RunCreateRequest(
        job_type=JobType.road,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="fuse roads"),
        target_crs="EPSG:32643",
        field_mapping={},
        debug=False,
    )
    plan = WorkflowPlan.model_validate(
        {
            "workflow_id": "wf_stage",
            "trigger": run_request.trigger.model_dump(),
            "context": {
                "intent": {"job_type": "road"},
                "retrieval": {"candidate_patterns": []},
                "selection_reason": "initial",
                "llm_provider": "mock",
                "plan_revision": 1,
            },
            "tasks": [],
            "expected_output": "road output",
        }
    )

    execution_path = tmp_path / "road.shp"
    execution_path.write_text("dummy", encoding="utf-8")
    artifact = RunArtifactMeta(filename="road.zip", path=str(tmp_path / "road.zip"), size_bytes=3)

    called: list[str] = []

    class StubService:
        def run_planning_stage(self, run_id: str, request: RunCreateRequest) -> WorkflowPlan:
            called.append(f"plan:{run_id}:{request.job_type.value}")
            return plan

        def run_validation_stage(self, run_id: str, plan: WorkflowPlan) -> WorkflowPlan:
            called.append(f"validate:{run_id}:{plan.workflow_id}")
            return plan

        def run_execution_stage(
            self,
            run_id: str,
            request: RunCreateRequest,
            plan: WorkflowPlan,
            osm_zip_path: Path,
            ref_zip_path: Path,
            intermediate_dir: Path,
            output_dir: Path,
        ):
            called.append(f"execute:{run_id}:{plan.workflow_id}")
            return execution_path, []

        def run_writeback_stage(
            self,
            run_id: str,
            request: RunCreateRequest,
            plan: WorkflowPlan,
            fused_shp: Path,
            repair_records,
            output_dir: Path,
        ) -> RunArtifactMeta:
            called.append(f"writeback:{run_id}:{fused_shp.name}")
            return artifact

    monkeypatch.setattr(service_module, "agent_run_service", StubService())

    planned = worker_tasks.plan_run_task("run-1", run_request.model_dump(mode="json"))
    validated = worker_tasks.validate_run_task("run-1", planned)
    executed = worker_tasks.execute_plan_task(
        run_id="run-1",
        request=run_request.model_dump(mode="json"),
        plan=validated,
        osm_zip_path=str(tmp_path / "osm.zip"),
        ref_zip_path=str(tmp_path / "ref.zip"),
        intermediate_dir=str(tmp_path / "intermediate"),
        output_dir=str(tmp_path),
    )
    written = worker_tasks.writeback_run_task(
        run_id="run-1",
        request=run_request.model_dump(mode="json"),
        plan=validated,
        fused_shp_path=executed["fused_shp_path"],
        repair_records=executed["repair_records"],
        output_dir=str(tmp_path),
    )

    assert planned["workflow_id"] == "wf_stage"
    assert executed["fused_shp_path"] == str(execution_path)
    assert written["filename"] == "road.zip"
    assert called == [
        "plan:run-1:road",
        "validate:run-1:wf_stage",
        "execute:run-1:wf_stage",
        "writeback:run-1:road.shp",
    ]
