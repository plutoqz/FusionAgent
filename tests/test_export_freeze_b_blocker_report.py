from __future__ import annotations

import json
from pathlib import Path

from scripts.export_freeze_b_blocker_report import build_blocker_report


def _manifest_payload() -> dict:
    return {
        "manifest_id": "freeze-b-test",
        "freeze_line": "Freeze B",
        "cases": [
            {
                "case_id": "case.building.real.benin",
                "task_kind": "building",
                "data_tier": "real",
                "independence_label": "real_source",
                "claim_use": "quality_claim",
                "aoi": {"name": "benin", "bbox": [2.55, 9.25, 2.75, 9.45]},
                "sources": [{"source_id": "raw.osm.building", "version_token": "test"}],
                "baselines": [{"baseline_id": "fixed_adapter", "runner": "adapter_direct"}],
                "metrics": [{"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0}],
                "expected_artifact_roles": ["fused_vector"],
            },
            {
                "case_id": "case.building.synthetic.smoke",
                "task_kind": "building",
                "data_tier": "synthetic",
                "independence_label": "algorithm_generated",
                "claim_use": "smoke_only",
                "aoi": {"name": "synthetic", "bbox": [0, 0, 0.01, 0.01]},
                "sources": [],
                "baselines": [],
                "metrics": [],
                "expected_artifact_roles": ["fused_vector"],
            },
        ],
    }


def test_build_blocker_report_records_missing_source_root_and_precomputed_artifact(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps(_manifest_payload()), encoding="utf-8")
    output_json = tmp_path / "blocker.json"
    output_markdown = tmp_path / "blocker.md"

    payload = build_blocker_report(
        manifest,
        source_roots=[tmp_path / "missing-benin"],
        output_json=output_json,
        output_markdown=output_markdown,
    )

    assert payload["ready"] is False
    assert payload["source_root_available"] is False
    assert payload["blocking_case_count"] == 1
    assert payload["real_or_robustness_blocking_case_count"] == 1
    assert "Benin source root is unavailable" in payload["blocker_summary"]
    assert payload["cases"][0]["blocking_reason"] == "missing_precomputed_artifact_path"
    assert payload["cases"][1]["ready"] is True
    saved = json.loads(output_json.read_text(encoding="utf-8"))
    assert saved["manifest_id"] == "freeze-b-test"
    markdown = output_markdown.read_text(encoding="utf-8")
    assert "Freeze B Local Blocker Report" in markdown
    assert "case.building.real.benin" in markdown
