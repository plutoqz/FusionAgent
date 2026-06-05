from __future__ import annotations

import json
from pathlib import Path

from schemas.engineering_validation import EngineeringValidationCase, EngineeringValidationCaseResult
from schemas.scenario import ScenarioPhase, ScenarioRunResponse
from scripts.run_engineering_validation import (
    case_to_scenario_request,
    evaluate_case_summary,
    load_matrix_cases,
    main,
    run_validation_cases,
    write_validation_outputs,
)


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
    assert case.expected_task_kinds == []
    assert case.expected_failed_children_max is None
    assert case.expected_quality_checks == []
    assert case.degradation_mode is None


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
                "child_runs": [{"run_id": "run-a", "job_type": "building", "task_kind": "building", "phase": "succeeded"}],
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


def test_evaluate_case_summary_fails_when_expected_task_kinds_are_missing() -> None:
    case = EngineeringValidationCase(
        case_id="case-a",
        region_group="africa",
        aoi_class="small_city",
        scenario_name="A",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
        expected_task_kinds=["building", "road"],
    )

    passed, failures, observed = evaluate_case_summary(
        case,
        {
            "phase": "succeeded",
            "child_runs": [{"task_kind": "building", "phase": "succeeded"}],
            "quality": {},
            "failed_children": [],
        },
    )

    assert passed is False
    assert any("missing expected task kinds" in failure for failure in failures)
    assert observed["observed_task_kinds"] == ["building"]


def test_evaluate_case_summary_fails_when_failed_children_exceed_maximum() -> None:
    case = EngineeringValidationCase(
        case_id="case-a",
        region_group="africa",
        aoi_class="small_city",
        scenario_name="A",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
        expected_failed_children_max=1,
    )

    passed, failures, observed = evaluate_case_summary(
        case,
        {
            "phase": "partial",
            "child_runs": [{"task_kind": "building", "phase": "succeeded"}],
            "quality": {},
            "failed_children": [{"run_id": "failed-a"}, {"run_id": "failed-b"}],
        },
    )

    assert passed is False
    assert any("failed children expected at most 1, got 2" in failure for failure in failures)
    assert observed["failed_child_count"] == 2


def test_evaluate_case_summary_checks_expected_quality_checks_when_present() -> None:
    case = EngineeringValidationCase(
        case_id="case-a",
        region_group="africa",
        aoi_class="small_city",
        scenario_name="A",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
        expected_quality_checks=["geometry_type", "source_lineage", "required_fields"],
    )

    passed, failures, observed = evaluate_case_summary(
        case,
        {
            "phase": "succeeded",
            "child_runs": [{"task_kind": "building", "phase": "succeeded"}],
            "quality": {
                "checks": {
                    "geometry_type": True,
                    "source_lineage": {"passed": True},
                    "required_fields": {"status": "failed"},
                }
            },
            "failed_children": [],
        },
    )

    assert passed is False
    assert any("quality checks not passing" in failure for failure in failures)
    assert observed["quality_checks"] == {
        "geometry_type": True,
        "required_fields": False,
        "source_lineage": True,
    }


def test_evaluate_case_summary_reads_quality_checks_from_child_reports() -> None:
    case = EngineeringValidationCase(
        case_id="case-a",
        region_group="africa",
        aoi_class="small_city",
        scenario_name="A",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
        expected_quality_checks=["geometry_type", "source_lineage"],
    )

    passed, failures, observed = evaluate_case_summary(
        case,
        {
            "phase": "succeeded",
            "child_runs": [{"task_kind": "building", "phase": "succeeded"}],
            "quality": {
                "accepted_child_count": 1,
                "rejected_child_count": 0,
                "child_reports": [
                    {
                        "checks": {
                            "geometry_type": {"passed": True},
                            "source_lineage": {"passed": True},
                        }
                    }
                ],
            },
            "failed_children": [],
        },
    )

    assert passed is True
    assert failures == []
    assert observed["quality_checks"] == {"geometry_type": True, "source_lineage": True}


def test_evaluate_case_summary_fails_clearly_when_quality_check_is_missing_from_child_reports() -> None:
    case = EngineeringValidationCase(
        case_id="case-a",
        region_group="africa",
        aoi_class="small_city",
        scenario_name="A",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
        expected_quality_checks=["geometry_type", "source_lineage"],
    )

    passed, failures, observed = evaluate_case_summary(
        case,
        {
            "phase": "succeeded",
            "child_runs": [{"task_kind": "building", "phase": "succeeded"}],
            "quality": {
                "accepted_child_count": 1,
                "rejected_child_count": 0,
                "child_reports": [{"checks": {"geometry_type": {"passed": True}}}],
            },
            "failed_children": [],
        },
    )

    assert passed is False
    assert any("missing quality checks: ['source_lineage@child-1']" in failure for failure in failures)
    assert observed["quality_checks"] == {"geometry_type": True, "source_lineage": False}
    assert observed["quality_check_details"]["source_lineage"]["missing"] == ["child-1"]


def test_evaluate_case_summary_labels_summary_level_missing_quality_check_as_summary() -> None:
    case = EngineeringValidationCase(
        case_id="case-a",
        region_group="africa",
        aoi_class="small_city",
        scenario_name="A",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
        expected_quality_checks=["geometry_type"],
    )

    passed, failures, observed = evaluate_case_summary(
        case,
        {
            "phase": "succeeded",
            "child_runs": [{"task_kind": "building", "phase": "succeeded"}],
            "quality": {"checks": {"source_lineage": {"passed": True}}},
            "failed_children": [],
        },
    )

    assert passed is False
    assert any("missing quality checks: ['geometry_type@summary']" in failure for failure in failures)
    assert observed["quality_check_details"]["geometry_type"]["missing"] == ["summary"]


def test_evaluate_case_summary_adds_index_to_repeated_child_report_refs_without_run_id() -> None:
    case = EngineeringValidationCase(
        case_id="case-a",
        region_group="africa",
        aoi_class="small_city",
        scenario_name="A",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
        expected_quality_checks=["geometry_type"],
    )

    passed, failures, observed = evaluate_case_summary(
        case,
        {
            "phase": "succeeded",
            "child_runs": [{"task_kind": "building", "phase": "succeeded"}],
            "quality": {
                "child_reports": [
                    {"task_kind": "building", "checks": {"geometry_type": {"passed": True}}},
                    {"task_kind": "building", "checks": {"source_lineage": {"passed": True}}},
                    {"policy_id": "policy-a", "checks": {"source_lineage": {"passed": True}}},
                ]
            },
            "failed_children": [],
        },
    )

    assert passed is False
    assert any(
        "missing quality checks: ['geometry_type@building#2', 'geometry_type@policy-a#3']" in failure
        for failure in failures
    )
    assert observed["quality_check_details"]["geometry_type"]["missing"] == ["building#2", "policy-a#3"]


def test_evaluate_case_summary_distinguishes_required_job_types_from_task_kinds() -> None:
    case = EngineeringValidationCase(
        case_id="case-a",
        region_group="africa",
        aoi_class="small_city",
        scenario_name="A",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
        expected_required_tasks=["water"],
        expected_task_kinds=["waterways"],
    )

    passed, failures, observed = evaluate_case_summary(
        case,
        {
            "phase": "succeeded",
            "child_runs": [{"job_type": "water", "task_kind": "waterways", "phase": "succeeded"}],
            "quality": {},
            "failed_children": [],
        },
    )

    assert passed is True
    assert failures == []
    assert observed["observed_job_types"] == ["water"]
    assert observed["observed_task_kinds"] == ["waterways"]


def test_evaluate_case_summary_does_not_use_job_type_to_satisfy_expected_task_kinds() -> None:
    case = EngineeringValidationCase(
        case_id="case-a",
        region_group="africa",
        aoi_class="small_city",
        scenario_name="A",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
        expected_required_tasks=["road"],
        expected_task_kinds=["road"],
    )

    passed, failures, observed = evaluate_case_summary(
        case,
        {
            "phase": "succeeded",
            "child_runs": [{"job_type": "road", "phase": "succeeded"}],
            "quality": {},
            "failed_children": [],
        },
    )

    assert passed is False
    assert not any("missing required job types" in failure for failure in failures)
    assert any("missing expected task kinds: ['road']" in failure for failure in failures)
    assert observed["observed_job_types"] == ["road"]
    assert observed["observed_task_kinds"] == []
    assert observed["observed_task_identifiers"] == ["road"]


def test_evaluate_case_summary_fails_when_child_report_missing_expected_check() -> None:
    case = EngineeringValidationCase(
        case_id="case-a",
        region_group="africa",
        aoi_class="small_city",
        scenario_name="A",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
        expected_quality_checks=["geometry_type"],
    )

    passed, failures, observed = evaluate_case_summary(
        case,
        {
            "phase": "succeeded",
            "child_runs": [{"task_kind": "building", "phase": "succeeded"}],
            "quality": {
                "child_reports": [
                    {"run_id": "run-a", "checks": {"geometry_type": {"passed": True}}},
                    {"run_id": "run-b", "checks": {"source_lineage": {"passed": True}}},
                ],
            },
            "failed_children": [],
        },
    )

    assert passed is False
    assert any("missing quality checks: ['geometry_type@run-b']" in failure for failure in failures)
    assert observed["quality_check_details"]["geometry_type"]["missing"] == ["run-b"]


def test_evaluate_case_summary_fails_when_child_report_check_fails() -> None:
    case = EngineeringValidationCase(
        case_id="case-a",
        region_group="africa",
        aoi_class="small_city",
        scenario_name="A",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
        expected_quality_checks=["geometry_type"],
    )

    passed, failures, observed = evaluate_case_summary(
        case,
        {
            "phase": "succeeded",
            "child_runs": [{"task_kind": "building", "phase": "succeeded"}],
            "quality": {
                "child_reports": [
                    {"run_id": "run-a", "checks": {"geometry_type": {"passed": True}}},
                    {"run_id": "run-b", "checks": {"geometry_type": {"passed": False}}},
                ],
            },
            "failed_children": [],
        },
    )

    assert passed is False
    assert any("quality checks not passing: ['geometry_type@run-b']" in failure for failure in failures)
    assert observed["quality_check_details"]["geometry_type"]["failed"] == ["run-b"]


def test_case_to_scenario_request_carries_validation_expectations_in_metadata() -> None:
    case = EngineeringValidationCase(
        case_id="case-a",
        region_group="africa",
        aoi_class="bounded_large",
        scenario_name="A",
        disaster_type="flood",
        spatial_extent="bbox(0,0,1,1)",
        default_task_bundle=["building", "road"],
        expected_task_kinds=["building"],
        expected_failed_children_max=1,
        expected_quality_checks=["geometry_type"],
        degradation_mode="single_source_fallback",
    )

    request = case_to_scenario_request(case, output_root="runs/test")

    assert request.metadata["engineering_validation"] == {
        "expected_task_kinds": ["building"],
        "expected_failed_children_max": 1,
        "expected_quality_checks": ["geometry_type"],
        "degradation_mode": "single_source_fallback",
    }


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
