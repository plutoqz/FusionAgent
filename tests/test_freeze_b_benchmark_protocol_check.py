from __future__ import annotations

import json
from pathlib import Path

from scripts.freeze_b_benchmark_protocol_check import check_freeze_b_manifest


def test_freeze_b_manifest_check_reports_required_coverage(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_id": "freeze-b-v1",
                "freeze_line": "Freeze B",
                "cases": [
                    {
                        "case_id": "case.building.real",
                        "task_kind": "building",
                        "data_tier": "real",
                        "independence_label": "real_source",
                        "claim_use": "quality_claim",
                        "aoi": {"bbox": [0, 0, 1, 1]},
                        "sources": [{"source_id": "fixture", "version_token": "test"}],
                        "baselines": [{"baseline_id": "fixed_adapter", "runner": "adapter_direct"}],
                        "metrics": [{"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    report = check_freeze_b_manifest(manifest)

    assert report["manifest_id"] == "freeze-b-v1"
    assert report["case_count"] == 1
    assert report["synthetic_quality_claim_violations"] == []
