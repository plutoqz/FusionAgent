from __future__ import annotations

import json
from pathlib import Path


MATRIX = Path("docs/superpowers/validation/engineering_validation_matrix.yaml")


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


def test_engineering_validation_runner_dry_run_lists_cases(capsys) -> None:
    from scripts.run_engineering_validation import main

    exit_code = main(["--matrix", str(MATRIX), "--dry-run"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "pakistan_karachi_small_city" in captured.out
    assert "africa_kenya_bounded_large" in captured.out
