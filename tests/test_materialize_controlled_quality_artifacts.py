from __future__ import annotations

import json
from pathlib import Path

from scripts.materialize_controlled_quality_artifacts import materialize_controlled_quality_artifacts
from scripts.run_fusion_quality_benchmark import run_manifest


def test_materialize_controlled_quality_artifacts_can_feed_quality_benchmark(tmp_path: Path) -> None:
    manifest = tmp_path / "controlled-manifest.json"
    output_dir = tmp_path / "controlled"

    result = materialize_controlled_quality_artifacts(output_dir=output_dir, manifest_path=manifest)
    payload = json.loads(manifest.read_text(encoding="utf-8"))

    assert result["artifact_count"] == 4
    assert payload["manifest_id"] == "freeze-b-controlled-supplement-v1"
    assert {case["case_id"] for case in payload["cases"]} == {
        "case.road.semi_real.perturbed",
        "case.water_polygon.semi_real.priority_merge",
        "case.waterways.semi_real.line_conflation",
        "case.poi.semi_real.neighbor_match",
    }
    assert all(Path(case["precomputed_artifact_path"]).exists() for case in payload["cases"])

    summary = run_manifest(manifest, output_dir=tmp_path / "quality-out")

    assert summary["manifest_id"] == "freeze-b-controlled-supplement-v1"
    assert summary["result_count"] == 4
    assert summary["quality_claim_case_count"] == 0
    assert summary["robustness_claim_case_count"] == 4
    assert summary["accepted_quality_claim_count"] == 0
    assert summary["accepted_robustness_claim_count"] == 4
    assert summary["accepted_non_smoke_claim_count"] == 4
    assert all(result["accepted_for_claim"] for result in summary["results"])
