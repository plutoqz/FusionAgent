from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from services.scenario_registry_service import ScenarioRegistryService


def test_list_scenario_runs_from_registry(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", str(tmp_path))
    service = ScenarioRegistryService(output_root=tmp_path)
    service.record(
        {
            "scenario_id": "scenario-a",
            "scenario_name": "Parakou earthquake",
            "phase": "succeeded",
            "output_dir": str(tmp_path / "scenario-a"),
            "child_run_ids": [],
            "created_at": "2026-04-21T00:00:00+00:00",
            "case_id": "parakou_earthquake_building_road",
        }
    )

    response = TestClient(create_app()).get("/api/v2/scenario-runs", params={"phase": "succeeded"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["records"][0]["scenario_id"] == "scenario-a"
    assert payload["records"][0]["phase"] == "succeeded"


def test_inspect_scenario_run_summary_from_registry(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("GEOFUSION_SCENARIO_OUTPUT_ROOT", str(tmp_path))
    scenario_dir = tmp_path / "scenario-a"
    scenario_dir.mkdir()
    (scenario_dir / "scenario_summary.json").write_text(
        json.dumps({"scenario_id": "scenario-a", "scenario_name": "Parakou earthquake"}),
        encoding="utf-8",
    )

    response = TestClient(create_app()).get("/api/v2/scenario-runs/scenario-a")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["scenario_name"] == "Parakou earthquake"
