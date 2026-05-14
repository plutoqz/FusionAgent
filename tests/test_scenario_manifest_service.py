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
    building_case = next(case for case in manifest.cases if case.case_id == "nairobi_building_single")
    assert building_case.spatial_extent == "bbox(36.79,-1.31,36.81,-1.29)"


def test_manifest_capability_checks_load(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
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

    manifest = load_scenario_manifest(manifest_path)

    assert manifest.cases[0].capability_checks.required_job_types == [JobType.road]
    assert manifest.cases[0].capability_checks.required_workflow_steps == ["aoi_resolved", "plan_validated"]
    assert manifest.cases[0].capability_checks.min_succeeded_children == 1
    assert manifest.cases[0].capability_checks.require_aoi_resolved is True


def test_manifest_spatial_extent_loads_and_converts_to_request(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_id": "scenario.paper.demo.v1",
                "cases": [
                    {
                        "case_id": "nairobi_building_single",
                        "scenario_name": "Nairobi building",
                        "trigger_content": "need building data for Nairobi, Kenya",
                        "job_types": ["building"],
                        "spatial_extent": "bbox(36.79,-1.31,36.81,-1.29)",
                        "expected_phase": ["succeeded", "partial"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    manifest = load_scenario_manifest(manifest_path)
    request = scenario_case_to_request(manifest.cases[0], output_root=str(tmp_path / "runs"))

    assert manifest.cases[0].spatial_extent == "bbox(36.79,-1.31,36.81,-1.29)"
    assert request.spatial_extent == "bbox(36.79,-1.31,36.81,-1.29)"
