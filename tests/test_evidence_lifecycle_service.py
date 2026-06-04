from __future__ import annotations

import json
from pathlib import Path

from schemas.evidence_lifecycle import EvidenceArtifactRef, EvidenceBundleManifest, ValidationSessionManifest
from services.evidence_lifecycle_service import build_run_evidence_manifest, build_scenario_evidence_manifest


def test_evidence_bundle_manifest_serializes_roles() -> None:
    manifest = EvidenceBundleManifest(
        bundle_id="run-1",
        bundle_kind="run",
        source_of_truth=["run.json", "plan.json", "audit.jsonl"],
        artifacts=[
            EvidenceArtifactRef(
                role="canonical_output",
                path="runs/run-1/output/building_fusion_result.zip",
                required=True,
                retention_class="durable_evidence",
            )
        ],
    )

    payload = manifest.model_dump(mode="json")

    assert payload["bundle_kind"] == "run"
    assert payload["artifacts"][0]["role"] == "canonical_output"
    assert payload["artifacts"][0]["retention_class"] == "durable_evidence"


def test_build_run_evidence_manifest_marks_existing_core_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-1"
    output_dir = run_dir / "output"
    output_dir.mkdir(parents=True)
    for name in ["run.json", "plan.json", "validation.json", "audit.jsonl"]:
        (run_dir / name).write_text("{}", encoding="utf-8")
    (output_dir / "quality_report.json").write_text("{}", encoding="utf-8")
    (output_dir / "building_fusion_result.zip").write_bytes(b"zip")

    manifest = build_run_evidence_manifest(run_dir)

    assert manifest.bundle_id == "run-1"
    assert manifest.bundle_kind == "run"
    assert "run.json" in manifest.source_of_truth
    assert any(item.role == "quality_report" and item.exists for item in manifest.artifacts)
    assert any(item.role == "canonical_output" and item.exists for item in manifest.artifacts)


def test_build_scenario_evidence_manifest_links_child_runs(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "scenario_1"
    scenario_dir.mkdir()
    (scenario_dir / "scenario_summary.json").write_text(
        json.dumps(
            {
                "scenario_id": "scenario_1",
                "child_runs": [{"run_id": "run-a"}, {"run_id": "run-b"}],
                "final_outputs": ["runs/run-a/output/building_fusion_result.zip"],
            }
        ),
        encoding="utf-8",
    )

    manifest = build_scenario_evidence_manifest(scenario_dir)

    assert manifest.bundle_id == "scenario_1"
    assert manifest.related_run_ids == ["run-a", "run-b"]
    assert any(item.role == "scenario_summary" for item in manifest.artifacts)
    assert any(item.role == "child_output" for item in manifest.artifacts)


def test_validation_session_manifest_tracks_matrix_and_outputs() -> None:
    manifest = ValidationSessionManifest(
        session_id="validation-20260604-120000",
        matrix_path="docs/superpowers/validation/engineering_validation_matrix.yaml",
        output_root="runs/engineering-validation/validation-20260604-120000",
        case_result_paths=["case_results.jsonl"],
        summary_path="validation_summary.json",
    )

    payload = manifest.model_dump(mode="json")

    assert payload["session_id"].startswith("validation-")
    assert payload["case_result_paths"] == ["case_results.jsonl"]
