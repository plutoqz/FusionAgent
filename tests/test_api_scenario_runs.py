from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import create_app
import api.routers.scenario_runs as scenario_runs_router
from schemas.scenario import ScenarioPhase, ScenarioRunResponse


def test_create_scenario_run_generates_summary_and_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", str(tmp_path))
    monkeypatch.setattr(scenario_runs_router, "scenario_run_service", _FakeScenarioService(str(tmp_path)))

    client = TestClient(create_app())
    response = client.post(
        "/api/v2/scenario-runs",
        json={
            "scenario_name": "Parakou earthquake",
            "trigger_content": "fuse building and road data for Parakou, Benin after an earthquake",
            "disaster_type": "earthquake",
            "job_types": ["building", "road"],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] in {"succeeded", "partial"}
    assert payload["output_dir"].startswith(str(tmp_path))


def test_create_scenario_run_accepts_spatial_extent(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", str(tmp_path))
    fake_service = _FakeScenarioService(str(tmp_path))
    monkeypatch.setattr(scenario_runs_router, "scenario_run_service", fake_service)

    client = TestClient(create_app())
    response = client.post(
        "/api/v2/scenario-runs",
        json={
            "scenario_name": "Nairobi building",
            "trigger_content": "need building data for Nairobi, Kenya",
            "job_types": ["building"],
            "spatial_extent": "bbox(36.79,-1.31,36.81,-1.29)",
        },
    )

    assert response.status_code == 200
    assert fake_service.last_request is not None
    assert fake_service.last_request.spatial_extent == "bbox(36.79,-1.31,36.81,-1.29)"


def test_create_scenario_run_returns_422_for_out_of_scope_request(monkeypatch):
    class _RejectingScenarioService:
        def create_scenario_run(self, request):
            raise ValueError(
                "UNSUPPORTED_EVENT_FEED_EXPECTATION: "
                "Scenario layer is bounded orchestration, not live event-feed simulation."
            )

    monkeypatch.setattr(scenario_runs_router, "scenario_run_service", _RejectingScenarioService())

    client = TestClient(create_app())
    response = client.post(
        "/api/v2/scenario-runs",
        json={
            "scenario_name": "Global traffic telemetry replay",
            "trigger_content": "simulate live event-feed with full digital twin outputs",
            "job_types": ["road"],
        },
    )

    assert response.status_code == 422
    assert "UNSUPPORTED_EVENT_FEED_EXPECTATION" in response.json()["detail"]


class _FakeScenarioService:
    def __init__(self, output_dir: str) -> None:
        self.output_dir = output_dir
        self.last_request = None

    def create_scenario_run(self, request):
        self.last_request = request
        return ScenarioRunResponse(
            scenario_id="scenario-test",
            phase=ScenarioPhase.succeeded,
            output_dir=self.output_dir,
            child_run_ids=["run-building", "run-road"],
        )
