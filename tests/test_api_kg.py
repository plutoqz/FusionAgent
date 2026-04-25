from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from api.app import create_app
import api.routers.kg as kg_router
import api.routers.runs_v2 as runs_v2_router
from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import (
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


def _build_plan() -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id="wf-api-kg",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="need building data"),
        context={
            "retrieval": {
                "candidate_patterns": [
                    {
                        "pattern_id": "wp.flood.building.default",
                        "pattern_name": "Flood Building Default",
                        "steps": [
                            {
                                "algorithm_id": "algo.fusion.building.v1",
                                "input_data_type": "dt.building.bundle",
                                "output_data_type": "dt.building.fused",
                                "data_source_id": "catalog.flood.building",
                            }
                        ],
                    }
                ],
                "data_sources": [{"source_id": "catalog.flood.building", "source_name": "Flood Building Bundle"}],
            },
            "grounding_report": {
                "grounded": True,
                "grounded_step_count": 1,
                "total_step_count": 1,
                "grounding_score": 1.0,
                "steps": [
                    {
                        "step": 1,
                        "algorithm_id": "algo.fusion.building.v1",
                        "input_data_type": "dt.building.bundle",
                        "data_source_id": "catalog.flood.building",
                        "output_data_type": "dt.building.fused",
                        "algorithm_grounded": True,
                        "algorithm_known": True,
                        "data_source_known": True,
                        "output_type_matches_intent": True,
                        "schema_policy_known": True,
                        "pattern_ids": ["wp.flood.building.default"],
                        "issue_codes": [],
                        "evidence_refs": ["plan.task(step=1).algorithm_id"],
                    }
                ],
            },
        },
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id="algo.fusion.building.v1",
                input=WorkflowTaskInput(
                    data_type_id="dt.building.bundle",
                    data_source_id="catalog.flood.building",
                ),
                output=WorkflowTaskOutput(data_type_id="dt.building.fused"),
                kg_validated=True,
            )
        ],
        expected_output="building result",
        validation=ValidationReport(valid=True, inserted_transform_steps=0, issues=[]),
    )


def _build_status(phase: RunPhase) -> RunStatus:
    return RunStatus(
        run_id="run-kg",
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="need building data"),
        phase=phase,
        progress=100 if phase == RunPhase.succeeded else 0,
        target_crs="EPSG:32643",
        debug=False,
        created_at="2026-04-25T00:00:00+00:00",
        updated_at="2026-04-25T00:05:00+00:00",
    )


class StubRunService:
    def __init__(self, status: RunStatus, plan: WorkflowPlan | None) -> None:
        self._status = status
        self._plan = plan

    def get_run(self, run_id: str) -> RunStatus | None:
        return self._status if run_id == self._status.run_id else None

    def get_plan(self, run_id: str) -> WorkflowPlan | None:
        if run_id != self._status.run_id:
            return None
        return self._plan

    def get_audit_events(self, run_id: str) -> list[object]:
        return []

    def get_artifact_path(self, run_id: str):
        return None


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("GEOFUSION_KG_BACKEND", "memory")
    monkeypatch.setattr(kg_router, "create_kg_repository", lambda: InMemoryKGRepository())
    status = _build_status(RunPhase.succeeded)
    monkeypatch.setattr(runs_v2_router, "agent_run_service", StubRunService(status=status, plan=_build_plan()))
    return TestClient(create_app())


def test_kg_overview_endpoint_returns_graph(client: TestClient) -> None:
    resp = client.get("/api/v2/kg/overview")

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["meta"]["graph_type"] == "overview"
    assert any(node["kind"] == "workflow_pattern" for node in payload["nodes"])
    assert any(edge["relationship"] == "uses_algorithm" for edge in payload["edges"])


def test_run_kg_graph_endpoint_returns_per_run_graph(client: TestClient) -> None:
    resp = client.get("/api/v2/runs/run-kg/kg-graph")

    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["meta"]["graph_type"] == "run_path"
    assert payload["meta"]["workflow_id"] == "wf-api-kg"
    assert any(node["id"] == "task:1" and node["kind"] == "task" for node in payload["nodes"])
    assert any(edge["relationship"] == "executes_algorithm" for edge in payload["edges"])


def test_run_kg_graph_endpoint_returns_404_when_plan_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status = _build_status(RunPhase.succeeded)
    monkeypatch.setattr(kg_router, "create_kg_repository", lambda: InMemoryKGRepository())
    monkeypatch.setattr(runs_v2_router, "agent_run_service", StubRunService(status=status, plan=None))
    client = TestClient(create_app())

    resp = client.get("/api/v2/runs/run-kg/kg-graph")

    assert resp.status_code == 404
    assert resp.json() == {"detail": "Plan not found"}


@pytest.mark.parametrize("phase", [RunPhase.queued, RunPhase.planning])
def test_run_kg_graph_endpoint_returns_409_when_plan_not_ready(
    monkeypatch: pytest.MonkeyPatch,
    phase: RunPhase,
) -> None:
    monkeypatch.setattr(kg_router, "create_kg_repository", lambda: InMemoryKGRepository())
    monkeypatch.setattr(runs_v2_router, "agent_run_service", StubRunService(status=_build_status(phase), plan=None))
    client = TestClient(create_app())

    resp = client.get("/api/v2/runs/run-kg/kg-graph")

    assert resp.status_code == 409
    assert resp.json() == {"detail": f"Plan not ready yet: {phase.value}"}
