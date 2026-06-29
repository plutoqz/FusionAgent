from __future__ import annotations

import json
from pathlib import Path

from scripts.check_quality_benchmark_readiness import check_readiness


def _manifest_payload(*, artifact_path: str | None) -> dict:
    case = {
        "case_id": "case.precomputed.building",
        "task_kind": "building",
        "data_tier": "real",
        "independence_label": "real_source",
        "claim_use": "quality_claim",
        "aoi": {"bbox": [0, 0, 1, 1]},
        "sources": [{"source_id": "fixture", "version_token": "test"}],
        "baselines": [{"baseline_id": "fixed_adapter", "runner": "adapter_direct"}],
        "metrics": [{"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0}],
        "expected_artifact_roles": ["fused_vector"],
    }
    if artifact_path is not None:
        case["precomputed_artifact_path"] = artifact_path
    return {"manifest_id": "test-freeze-b", "freeze_line": "Freeze B", "cases": [case]}


def test_check_readiness_reports_missing_precomputed_artifact_path(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_manifest_payload(artifact_path=None)), encoding="utf-8")

    payload = check_readiness(
        manifest,
        output_json=tmp_path / "readiness.json",
        output_markdown=tmp_path / "readiness.md",
    )

    assert payload["ready"] is False
    assert payload["blocking_case_count"] == 1
    assert payload["cases"][0]["blocking_reason"] == "missing_precomputed_artifact_path"


def test_check_readiness_accepts_existing_artifact_path(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.gpkg"
    artifact.write_text("placeholder", encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_manifest_payload(artifact_path=str(artifact))), encoding="utf-8")

    payload = check_readiness(manifest, output_json=tmp_path / "readiness.json")

    assert payload["ready"] is True
    assert payload["blocking_case_count"] == 0
