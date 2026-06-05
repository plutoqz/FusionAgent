from __future__ import annotations

import json
from pathlib import Path


MATRIX = Path("docs/superpowers/validation/engineering_validation_matrix.yaml")
QUALITY_CHECK_IDS = {
    "readable",
    "non_empty",
    "required_fields",
    "geometry_type",
    "aoi_intersection",
    "source_lineage",
    "multi_source_lineage",
    "duplicate_geometry_rate",
    "invalid_geometry_rate",
    "source_contribution_balance",
}


def _load_matrix() -> dict:
    return json.loads(MATRIX.read_text(encoding="utf-8"))


def test_engineering_validation_matrix_has_required_aoi_classes_and_regions() -> None:
    payload = _load_matrix()
    cases = payload["cases"]

    assert {case["aoi_class"] for case in cases} == {"small_city", "medium_region", "bounded_large"}
    assert {"pakistan", "africa"} <= {case["region_group"] for case in cases}
    for case in cases:
        assert case["default_task_bundle"] == ["building", "road", "water_polygon", "waterways", "poi"]
        assert case["output_format"] == "GPKG"
        assert "bbox" in case or "spatial_extent" in case
        assert "expected_min_succeeded_children" in case
        assert "expected_required_tasks" in case
        assert "quality_policy_id" in case


def test_engineering_validation_matrix_expands_disaster_task_and_degradation_coverage() -> None:
    payload = _load_matrix()
    cases = payload["cases"]

    disaster_counts: dict[str, int] = {}
    for case in cases:
        disaster_counts[case["disaster_type"]] = disaster_counts.get(case["disaster_type"], 0) + 1

    assert len(cases) >= 12
    assert disaster_counts.get("flood", 0) >= 4
    assert disaster_counts.get("earthquake", 0) >= 2
    assert disaster_counts.get("typhoon", 0) >= 1
    assert sum(1 for case in cases if case.get("expected_task_kinds")) >= 2
    assert {
        "missing_reference_source",
        "single_source_fallback",
        "bounded_large_timeout_retry_evidence",
    } <= {case.get("degradation_mode") for case in cases}


def test_engineering_validation_matrix_uses_task_kind_expectations_selectively() -> None:
    payload = _load_matrix()
    identical_expectation_cases = [
        case["case_id"]
        for case in payload["cases"]
        if case.get("expected_task_kinds")
        and case.get("expected_task_kinds") == case.get("expected_required_tasks")
    ]

    assert len(identical_expectation_cases) <= 3


def test_engineering_validation_matrix_uses_observable_quality_check_ids() -> None:
    payload = _load_matrix()

    for case in payload["cases"]:
        unexpected = set(case.get("expected_quality_checks") or []) - QUALITY_CHECK_IDS
        assert unexpected == set(), f"{case['case_id']} has unsupported quality checks: {sorted(unexpected)}"


def test_engineering_validation_matrix_avoids_brittle_zero_failed_children_for_live_cases() -> None:
    payload = _load_matrix()

    zero_tolerance_cases = [
        case["case_id"]
        for case in payload["cases"]
        if case.get("expected_failed_children_max") == 0
    ]

    assert zero_tolerance_cases == ["bangladesh_dhaka_building_road_focus"]


def test_engineering_validation_runner_dry_run_lists_cases(capsys) -> None:
    from scripts.run_engineering_validation import main

    exit_code = main(["--matrix", str(MATRIX), "--dry-run"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "pakistan_karachi_small_city" in captured.out
    assert "africa_kenya_bounded_large" in captured.out
