from __future__ import annotations

import json
from pathlib import Path

from schemas.engineering_validation import EngineeringValidationCase, EngineeringValidationCaseResult
from schemas.scenario import ScenarioPhase, ScenarioRunResponse
from scripts.run_engineering_validation import load_matrix_cases, main, run_validation_cases, write_validation_outputs


def test_engineering_validation_case_requires_core_fields() -> None:
    case = EngineeringValidationCase(
        case_id="pakistan_karachi_small_city",
        region_group="pakistan",
        aoi_class="small_city",
        scenario_name="Karachi flood",
        disaster_type="flood",
        spatial_extent="bbox(66.95,24.78,67.20,25.02)",
        default_task_bundle=["building", "road"],
        output_format="GPKG",
    )

    assert case.case_id == "pakistan_karachi_small_city"
    assert case.expected_min_succeeded_children == 1


def test_engineering_validation_result_serializes_failure_reasons() -> None:
    result = EngineeringValidationCaseResult(
        case_id="case-1",
        passed=False,
        phase="partial",
        failure_reasons=["quality_failed"],
    )

    assert result.model_dump(mode="json")["failure_reasons"] == ["quality_failed"]


def test_load_matrix_cases_filters_by_case_id(tmp_path: Path) -> None:
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "version": "test",
                "cases": [
                    {
                        "case_id": "case-a",
                        "region_group": "africa",
                        "aoi_class": "small_city",
                        "scenario_name": "A",
                        "disaster_type": "flood",
                        "spatial_extent": "bbox(0,0,1,1)",
                        "default_task_bundle": ["building"],
                    },
                    {
                        "case_id": "case-b",
                        "region_group": "pakistan",
                        "aoi_class": "medium_region",
                        "scenario_name": "B",
                        "disaster_type": "flood",
                        "spatial_extent": "bbox(1,1,2,2)",
                        "default_task_bundle": ["road"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    cases = load_matrix_cases(matrix, selected_case_ids=["case-b"])

    assert [case.case_id for case in cases] == ["case-b"]


class FakeScenarioClient:
    def create_scenario_run(self, request):
        return ScenarioRunResponse(
            scenario_id="scenario-1",
            phase=ScenarioPhase.succeeded,
            output_dir=str(self.output_dir),
            child_run_ids=["run-a"],
        )


def test_run_validation_cases_reads_summary_and_marks_passed(tmp_path: Path) -> None:
    output_dir = tmp_path / "scenario-1"
    output_dir.mkdir()
    (output_dir / "scenario_summary.json").write_text(
        json.dumps(
            {
                "scenario_id": "scenario-1",
                "phase": "succeeded",
                "child_runs": [{"run_id": "run-a", "task_kind": "building", "phase": "succeeded"}],
                "quality": {"accepted": True, "failed_children_count": 0},
                "failed_children": [],
            }
        ),
        encoding="utf-8",
    )
    client = FakeScenarioClient()
    client.output_dir = output_dir
    case = EngineeringValidationCase(
        case_id="case-a",
        region_group="africa",
        aoi_class="small_city",
        scenario_name="A",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
        default_task_bundle=["building"],
        expected_required_tasks=["building"],
    )

    results = run_validation_cases([case], output_root=str(tmp_path), client=client)

    assert results[0].passed is True
    assert results[0].scenario_id == "scenario-1"


def test_write_validation_outputs_creates_session_files(tmp_path: Path) -> None:
    result = EngineeringValidationCaseResult(case_id="case-a", passed=True, phase="succeeded")
    summary = write_validation_outputs(
        session_id="validation-test",
        matrix_path=Path("matrix.json"),
        output_root=tmp_path,
        cases=[],
        results=[result],
        metadata={"base_url": "http://127.0.0.1:8000"},
    )

    assert summary.passed_cases == 1
    assert (tmp_path / "validation_session.json").exists()
    assert (tmp_path / "case_results.jsonl").exists()
    assert (tmp_path / "validation_summary.json").exists()
    assert (tmp_path / "validation_summary.md").exists()


def test_main_dry_run_filters_selected_case(tmp_path: Path, capsys) -> None:
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "version": "test",
                "cases": [
                    {
                        "case_id": "case-a",
                        "region_group": "africa",
                        "aoi_class": "small_city",
                        "scenario_name": "A",
                        "disaster_type": "flood",
                        "spatial_extent": "bbox(0,0,1,1)",
                        "default_task_bundle": ["building"],
                    },
                    {
                        "case_id": "case-b",
                        "region_group": "pakistan",
                        "aoi_class": "medium_region",
                        "scenario_name": "B",
                        "disaster_type": "flood",
                        "spatial_extent": "bbox(1,1,2,2)",
                        "default_task_bundle": ["road"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    exit_code = main(["--matrix", str(matrix), "--dry-run", "--case", "case-b"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "case-b" in captured.out
    assert "case-a" not in captured.out
