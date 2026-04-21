from __future__ import annotations

import json
from pathlib import Path

from schemas.scenario import ScenarioPhase, ScenarioRunResponse
from scripts.scenario_eval_harness import run_manifest_cases


def test_run_manifest_cases_summarizes_fake_client_response(tmp_path: Path):
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

    summary = run_manifest_cases(manifest_path, str(tmp_path / "runs"), _FakeScenarioClient())

    assert summary.total_cases == 1
    assert summary.passed_cases == 1
    assert summary.results[0].scenario_id == "scenario-a"


class _FakeScenarioClient:
    def create_scenario_run(self, request):
        assert request.metadata["case_id"] == "parakou_earthquake_building_road"
        return ScenarioRunResponse(
            scenario_id="scenario-a",
            phase=ScenarioPhase.succeeded,
            output_dir="scenario-output",
            child_run_ids=["run-building"],
        )
