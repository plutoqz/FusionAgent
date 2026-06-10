from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from scripts.run_fusion_quality_benchmark import run_manifest


def test_run_manifest_summarizes_precomputed_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.gpkg"
    gpd.GeoDataFrame(
        [{"source_id": "osm", "source_feature_id": "b1", "geometry": Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])}],
        crs="EPSG:4326",
    ).to_file(artifact, driver="GPKG")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_id": "test-freeze-b",
                "freeze_line": "Freeze B",
                "cases": [
                    {
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
                        "precomputed_artifact_path": str(artifact),
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    summary = run_manifest(manifest_path, output_dir=tmp_path / "out")

    assert summary["manifest_id"] == "test-freeze-b"
    assert summary["result_count"] == 1
    assert summary["results"][0]["accepted_for_claim"] is True
