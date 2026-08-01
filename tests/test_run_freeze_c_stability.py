from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from scripts.run_freeze_c_stability import (
    _assert_new_directory,
    build_run_snapshot,
    compare_snapshots,
)


def _write_bundle(
    root: Path,
    *,
    artifact_bytes: bytes = b"artifact",
    feature_count: int = 3,
    run_name: str = "random-run",
) -> None:
    case_dir = root / "cases" / "C02"
    case_dir.mkdir(parents=True, exist_ok=True)
    runtime_output = root / "runtime" / "runs" / run_name / "output"
    runtime_output.mkdir(parents=True, exist_ok=True)
    artifact = runtime_output / "water_fusion_result.zip"
    artifact.write_bytes(artifact_bytes)
    (case_dir / "prepared_inputs_priority_delivery.json").write_text("{\"source\": true}", encoding="utf-8")
    (case_dir / "case_result.json").write_text(
        json.dumps(
            {
                "case_id": "C02",
                "passed": True,
                "final_phase": "partial_provisional",
                "final_task_order": ["water_polygon", "waterways", "road"],
                "gap_count": 2,
                "assertions": {"task_order_matches": True},
                "stage_evaluations": [],
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "planning_decision.json").write_text(
        json.dumps({"expected_layer_priority": ["water_polygon"], "actual_task_order": ["water_polygon"], "decision": "allow"}),
        encoding="utf-8",
    )
    (case_dir / "gap_declaration.json").write_text(
        json.dumps({"observed_gaps": [{"layer": "water_polygon", "gap_type": "source_unavailable", "source_ids": ["raw.test"]}]}),
        encoding="utf-8",
    )
    (case_dir / "delivery_manifest.json").write_text(
        json.dumps(
            {
                "final_phase": "partial_provisional",
                "outputs": [str(artifact)],
                "provisional_outputs": [
                    {
                        "task_kind": "water_polygon",
                        "task_family": "water",
                        "phase": "partial_provisional",
                        "provisional": True,
                        "fusion_mode": "single_source_degraded",
                        "missing_sources": ["raw.test"],
                        "_experiment_stage_id": "priority_delivery",
                        "artifact_path": str(artifact),
                    }
                ],
                "superseded_outputs": [],
            }
        ),
        encoding="utf-8",
    )
    (case_dir / "quality_gate_result.json").write_text(
        json.dumps(
            {
                "case_id": "C02",
                "accepted_child_count": 1,
                "rejected_child_count": 0,
                "final_phase": "partial_provisional",
                "stages": [],
                "child_reports": [{"task_kind": "water_polygon", "accepted": True, "metrics": {"feature_count": feature_count}}],
            }
        ),
        encoding="utf-8",
    )
    (root / "experiment_result.json").write_text(
        json.dumps({"experiment_id": "test", "all_cases_passed": True}),
        encoding="utf-8",
    )


def test_snapshots_ignore_run_ids_and_paths_but_compare_artifact_bytes(tmp_path: Path) -> None:
    first = tmp_path / "run-01"
    second = tmp_path / "run-02"
    _write_bundle(first)
    _write_bundle(second, run_name="another-run")

    comparison = compare_snapshots([build_run_snapshot(first), build_run_snapshot(second)])

    assert comparison["byte_level"]["stable"] is True
    assert comparison["semantic_level"]["stable"] is True


def test_comparison_reports_artifact_byte_and_feature_drift(tmp_path: Path) -> None:
    first = tmp_path / "run-01"
    second = tmp_path / "run-02"
    _write_bundle(first)
    _write_bundle(second, artifact_bytes=b"changed", feature_count=4)

    comparison = compare_snapshots([build_run_snapshot(first), build_run_snapshot(second)])

    assert comparison["byte_level"]["stable"] is False
    assert comparison["semantic_level"]["stable"] is False
    assert comparison["byte_level"]["differences"]
    assert comparison["semantic_level"]["differences"]


def test_zip_container_variation_is_classified_when_member_content_is_stable(tmp_path: Path) -> None:
    first = tmp_path / "run-01"
    second = tmp_path / "run-02"
    _write_bundle(first, artifact_bytes=b"placeholder")
    _write_bundle(second, artifact_bytes=b"placeholder", run_name="another-run")
    for root, date_time in ((first, (2020, 1, 1, 0, 0, 0)), (second, (2021, 1, 1, 0, 0, 0))):
        artifact = next((root / "runtime" / "runs").rglob("water_fusion_result.zip"))
        with zipfile.ZipFile(artifact, "w") as archive:
            info = zipfile.ZipInfo("artifact.txt", date_time=date_time)
            archive.writestr(info, b"same-content")

    comparison = compare_snapshots([build_run_snapshot(first), build_run_snapshot(second)])

    assert comparison["byte_level"]["stable"] is False
    assert comparison["semantic_level"]["stable"] is True
    assert comparison["allowed_fluctuations"]["unclassified_byte_differences"] == []


def test_p2_evidence_directory_is_protected(tmp_path: Path) -> None:
    evidence_root = tmp_path / "p2"
    evidence_root.mkdir()
    (evidence_root / "old.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError, match="非空"):
        _assert_new_directory(evidence_root)
