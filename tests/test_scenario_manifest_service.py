from __future__ import annotations

import json
from pathlib import Path

from schemas.fusion import JobType
from services.scenario_manifest_service import load_scenario_manifest, scenario_case_to_request


def test_load_scenario_manifest_and_convert_case_to_request(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_id": "scenario.paper.demo.v1",
                "cases": [
                    {
                        "case_id": "parakou_earthquake_building_road",
                        "scenario_name": "Parakou earthquake",
                        "trigger_content": "fuse building and road data for Parakou, Benin after an earthquake",
                        "disaster_type": "earthquake",
                        "job_types": ["building", "road"],
                        "expected_phase": ["succeeded", "partial"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_scenario_manifest(manifest_path)
    request = scenario_case_to_request(manifest.cases[0], output_root=str(tmp_path / "runs"))

    assert manifest.manifest_id == "scenario.paper.demo.v1"
    assert manifest.cases[0].case_id == "parakou_earthquake_building_road"
    assert manifest.cases[0].job_types == [JobType.building, JobType.road]
    assert request.metadata["case_id"] == "parakou_earthquake_building_road"
    assert request.output_root == str(tmp_path / "runs")


def test_checked_in_scenario_eval_manifest_loads():
    manifest = load_scenario_manifest(Path("docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json"))

    assert manifest.manifest_id == "scenario.paper.demo.v1"
    assert manifest.cases[0].case_id == "parakou_earthquake_building_road"
