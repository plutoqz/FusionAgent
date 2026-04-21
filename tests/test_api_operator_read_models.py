from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
import api.routers.runs_v2 as runs_v2_router
from schemas.agent import RunPhase, RunStatus, RunTrigger, RunTriggerType
from services.scenario_registry_service import ScenarioRegistryService


def test_api_lists_persisted_runs_from_registry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = tmp_path / "runs" / "run-a"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        '{"run_id":"run-a","phase":"succeeded","job_type":"building"}',
        encoding="utf-8",
    )

    response = TestClient(create_app()).get(
        "/api/v2/runs",
        params={"phase": "succeeded", "job_type": "building"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["records"][0]["run_id"] == "run-a"
    assert payload["records"][0]["run_dir"] == str(run_dir)


def test_api_runs_list_skips_undecodable_run_json(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    valid_run_dir = tmp_path / "runs" / "run-a"
    bad_run_dir = tmp_path / "runs" / "run-bad"
    valid_run_dir.mkdir(parents=True)
    bad_run_dir.mkdir(parents=True)
    (valid_run_dir / "run.json").write_text(
        '{"run_id":"run-a","phase":"succeeded","job_type":"building"}',
        encoding="utf-8",
    )
    (bad_run_dir / "run.json").write_bytes(b"\xff\xfe\x00")

    response = TestClient(create_app()).get("/api/v2/runs")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [record["run_id"] for record in payload["records"]] == ["run-a"]


def test_api_operator_summary_returns_runtime_and_recent_read_models(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", str(tmp_path / "scenarios"))
    monkeypatch.setenv("GEOFUSION_KG_BACKEND", "memory")
    monkeypatch.setenv("GEOFUSION_LLM_PROVIDER", "mock")
    monkeypatch.setenv("GEOFUSION_CELERY_EAGER", "1")
    monkeypatch.setenv("GEOFUSION_API_PORT", "8000")

    run_dir = tmp_path / "runs" / "run-a"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        '{"run_id":"run-a","phase":"succeeded","job_type":"building"}',
        encoding="utf-8",
    )
    ScenarioRegistryService(output_root=tmp_path / "scenarios").record(
        {"scenario_id": "scenario-a", "phase": "succeeded"}
    )

    response = TestClient(create_app()).get("/api/v2/operator/summary", params={"limit": 10})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["runtime"] == {
        "kg_backend": "memory",
        "llm_provider": "mock",
        "celery_eager": "1",
        "api_port": "8000",
    }
    assert payload["recent_runs"][0]["run_id"] == "run-a"
    assert payload["recent_scenarios"][0]["scenario_id"] == "scenario-a"
    assert payload["evidence_gaps"] == []


def test_api_runs_list_route_does_not_shadow_run_status_route(monkeypatch) -> None:
    class FakeAgentRunService:
        def get_run(self, run_id: str) -> RunStatus:
            return RunStatus(
                run_id=run_id,
                job_type="building",
                trigger=RunTrigger(type=RunTriggerType.user_query, content="inspect existing run"),
                phase=RunPhase.succeeded,
                target_crs="EPSG:4326",
                created_at="2026-04-21T00:00:00+00:00",
            )

    monkeypatch.setattr(runs_v2_router, "agent_run_service", FakeAgentRunService())

    response = TestClient(create_app()).get("/api/v2/runs/run-existing")

    assert response.status_code == 200, response.text
    assert response.json()["run_id"] == "run-existing"
