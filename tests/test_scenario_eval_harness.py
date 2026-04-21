from __future__ import annotations

import json
from pathlib import Path

from schemas.scenario import ScenarioPhase, ScenarioRunResponse
from scripts.scenario_eval_harness import run_manifest_cases


def test_run_manifest_cases_passes_when_summary_satisfies_capability_checks(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    output_dir = tmp_path / "scenario-a"
    output_dir.mkdir()
    (output_dir / "scenario_summary.json").write_text(
        json.dumps(
            {
                "child_runs": [{"job_type": "road", "phase": "succeeded"}],
                "workflow_traces": [
                    {
                        "steps": [
                            {"step_name": "aoi_resolved"},
                            {"step_name": "plan_validated"},
                            {"step_name": "task_inputs_resolved"},
                        ]
                    }
                ],
                "source_coverage": [{"job_type": "road"}],
            }
        ),
        encoding="utf-8",
    )
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
                        "job_types": ["road"],
                        "expected_phase": ["succeeded", "partial"],
                        "capability_checks": {
                            "required_job_types": ["road"],
                            "required_workflow_steps": ["aoi_resolved", "plan_validated"],
                            "min_succeeded_children": 1,
                            "require_aoi_resolved": True,
                            "require_task_inputs_resolved": True,
                            "require_source_coverage": True,
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = run_manifest_cases(
        manifest_path,
        str(tmp_path / "runs"),
        _FakeScenarioClient(output_dir=output_dir, expected_case_id="parakou_earthquake_building_road"),
    )

    assert summary.total_cases == 1
    assert summary.passed_cases == 1
    assert summary.results[0].scenario_id == "scenario-a"
    assert summary.results[0].capability_checks_passed is True
    assert summary.results[0].observed["succeeded_child_count"] == 1


def test_run_manifest_cases_fails_when_aoi_evidence_is_missing(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    output_dir = tmp_path / "scenario-b"
    output_dir.mkdir()
    (output_dir / "scenario_summary.json").write_text(
        json.dumps(
            {
                "child_runs": [{"job_type": "road", "phase": "succeeded"}],
                "workflow_traces": [{"steps": [{"step_name": "task_inputs_resolved"}]}],
                "source_coverage": [{"job_type": "road"}],
            }
        ),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_id": "scenario.paper.demo.v1",
                "cases": [
                    {
                        "case_id": "nairobi_flood_road_single",
                        "scenario_name": "Nairobi flood road",
                        "trigger_content": "fuse road data for Nairobi, Kenya after a flood",
                        "job_types": ["road"],
                        "expected_phase": ["succeeded", "partial"],
                        "capability_checks": {
                            "required_job_types": ["road"],
                            "required_workflow_steps": ["aoi_resolved", "plan_validated"],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    summary = run_manifest_cases(
        manifest_path,
        str(tmp_path / "runs"),
        _FakeScenarioClient(output_dir=output_dir, expected_case_id="nairobi_flood_road_single"),
    )

    assert summary.failed_cases == 1
    assert summary.results[0].passed is False
    assert "required_workflow_steps missing aoi_resolved" in summary.results[0].capability_failures[0]


class _FakeScenarioClient:
    def __init__(self, *, output_dir: Path, expected_case_id: str) -> None:
        self.output_dir = output_dir
        self.expected_case_id = expected_case_id

    def create_scenario_run(self, request):
        assert request.metadata["case_id"] == self.expected_case_id
        return ScenarioRunResponse(
            scenario_id="scenario-a",
            phase=ScenarioPhase.succeeded,
            output_dir=str(self.output_dir),
            child_run_ids=["run-building"],
        )
