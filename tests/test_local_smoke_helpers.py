from __future__ import annotations

from pathlib import Path

from utils.local_smoke import build_run_request_from_case, validate_smoke_result


def test_build_run_request_from_case_reads_golden_case_manifest(tmp_path: Path) -> None:
    case_dir = tmp_path / "building_disaster_flood"
    input_dir = case_dir / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "osm.zip").write_bytes(b"osm")
    (input_dir / "ref.zip").write_bytes(b"ref")
    (case_dir / "case.json").write_text(
        """
        {
          "case_id": "building_disaster_flood",
          "job_type": "building",
          "trigger": {
            "type": "disaster_event",
            "content": "flood building fusion",
            "disaster_type": "flood"
          },
          "osm_zip": "input/osm.zip",
          "ref_zip": "input/ref.zip"
        }
        """,
        encoding="utf-8",
    )

    payload = build_run_request_from_case(case_dir)

    assert payload["form"]["job_type"] == "building"
    assert payload["form"]["trigger_type"] == "disaster_event"
    assert payload["form"]["trigger_content"] == "flood building fusion"
    assert payload["form"]["disaster_type"] == "flood"
    assert payload["osm_zip_path"] == input_dir / "osm.zip"
    assert payload["ref_zip_path"] == input_dir / "ref.zip"


def test_validate_smoke_result_checks_plan_and_artifact_expectations() -> None:
    result = {
        "plan": {
            "context": {
                "retrieval": {
                    "candidate_patterns": [{"pattern_id": "wp.flood.building.default"}],
                    "algorithms": {
                        "algo.fusion.building.v1": {"algo_id": "algo.fusion.building.v1"},
                        "algo.fusion.building.safe": {"algo_id": "algo.fusion.building.safe"},
                    },
                }
            },
            "tasks": [
                {"algorithm_id": "algo.fusion.building.v1", "alternatives": ["algo.fusion.building.safe"]},
            ],
            "expected_output": "dt.building.fused",
        },
        "artifact_entries": ["result.shp", "result.shx", "result.dbf"],
    }

    validate_smoke_result(
        result,
        expected_plan_checks={
            "pattern_hint": "wp.flood.building.default",
            "required_algorithms": ["algo.fusion.building.v1", "algo.fusion.building.safe"],
            "required_output_type": "dt.building.fused",
        },
        artifact_checks={"required_suffixes": [".shp", ".shx", ".dbf"]},
    )
