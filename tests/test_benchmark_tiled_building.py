from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from scripts import benchmark_tiled_building
from services.tile_partition_service import TileManifest, TileSpec
from services.tiled_building_runtime_service import TiledBuildingRunResult


def _single_tile_manifest() -> TileManifest:
    return TileManifest(
        bbox=(2.48, 9.23, 2.77, 9.44),
        bbox_crs="EPSG:4326",
        working_crs="EPSG:32631",
        tile_width_m=5000.0,
        tile_height_m=5000.0,
        overlap_m=64.0,
        tiles=[
            TileSpec(
                tile_id="tile_000_000",
                bbox=(2.48, 9.23, 2.77, 9.44),
                buffered_bbox=(2.47, 9.22, 2.78, 9.45),
                working_bbox=(2.48, 9.23, 2.77, 9.44),
                working_buffered_bbox=(2.47, 9.22, 2.78, 9.45),
                row=0,
                col=0,
            )
        ],
    )


def test_benchmark_tiled_building_writes_expected_contract_outputs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    source_root = tmp_path / "source-root"
    output_root = tmp_path / "benchmark-output"
    osm_path = source_root / "osm.shp"
    ref_path = source_root / "ms.shp"
    output_shp = output_root / "runtime_output" / "fused_buildings.shp"
    output_shp.parent.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(
        {"osm_id": [1], "confidence": [0.95]},
        geometry=[box(2.500, 9.250, 2.505, 9.255)],
        crs="EPSG:32631",
    ).to_file(output_shp)

    profile_payload = {
        "profiles": [
            {"source_id": "raw.osm.building", "canonical_path": str(osm_path)},
            {"source_id": "raw.local.microsoft.building", "canonical_path": str(ref_path)},
        ]
    }
    manifest = _single_tile_manifest()

    monkeypatch.setattr(
        benchmark_tiled_building.SourceProfileService,
        "profile_benin_root",
        lambda self, root: profile_payload,
    )
    monkeypatch.setattr(
        benchmark_tiled_building.TilePartitionService,
        "partition_bbox",
        lambda self, **kwargs: manifest,
    )

    def fake_materialize_bbox_bundle(*, source_path: Path, request_bbox, output_zip: Path) -> Path:
        del source_path, request_bbox
        output_zip.parent.mkdir(parents=True, exist_ok=True)
        output_zip.write_bytes(b"zip")
        return output_zip

    def fake_clip_zip_to_request_bbox(_source_zip: Path, target_zip: Path, *, request_bbox) -> Path:
        del request_bbox
        target_zip.parent.mkdir(parents=True, exist_ok=True)
        target_zip.write_bytes(b"tile-zip")
        return target_zip

    def fake_run_tiled_building_job(self, **kwargs) -> TiledBuildingRunResult:
        on_event = kwargs["on_event"]
        on_event("tile_execution_started", {"tile_id": "tile_000_000"})
        on_event("tile_execution_completed", {"tile_id": "tile_000_000", "feature_count": 1})
        on_event(
            "tile_stitch_completed",
            {
                "tile_count": 1,
                "stitched_feature_count": 1,
                "output_shp": str(output_shp),
            },
        )
        return TiledBuildingRunResult(
            output_shp=output_shp,
            tile_count=1,
            stitched_feature_count=1,
            tile_outputs=[],
        )

    monkeypatch.setattr(
        benchmark_tiled_building,
        "_materialize_bbox_bundle",
        fake_materialize_bbox_bundle,
    )
    monkeypatch.setattr(
        benchmark_tiled_building,
        "clip_zip_to_request_bbox",
        fake_clip_zip_to_request_bbox,
    )
    monkeypatch.setattr(
        benchmark_tiled_building.TiledBuildingRuntimeService,
        "run_tiled_building_job",
        fake_run_tiled_building_job,
    )
    monkeypatch.setattr(
        benchmark_tiled_building.sys,
        "argv",
        [
            "benchmark_tiled_building.py",
            "--source-root",
            str(source_root),
            "--bbox",
            "2.48,9.23,2.77,9.44",
            "--target-crs",
            "EPSG:32631",
            "--output-root",
            str(output_root),
        ],
    )

    benchmark_tiled_building.main()

    source_profile_snapshot = json.loads(
        (output_root / "source_profile_snapshot.json").read_text(encoding="utf-8")
    )
    tile_manifest = json.loads(
        (output_root / "tile_manifest.json").read_text(encoding="utf-8")
    )
    timing = json.loads((output_root / "timing.json").read_text(encoding="utf-8"))
    summary = (output_root / "benchmark_summary.md").read_text(encoding="utf-8")

    assert [item["source_id"] for item in source_profile_snapshot["profiles"]] == [
        "raw.osm.building",
        "raw.local.microsoft.building",
    ]
    assert tile_manifest["tiles"][0]["tile_id"] == "tile_000_000"
    assert timing["tile_count"] == 1
    assert timing["stitched_feature_count"] == 1
    assert timing["final_feature_count"] == 1
    assert timing["selected_profiles"] == {
        "osm": "raw.osm.building",
        "reference": "raw.local.microsoft.building",
    }
    assert "# Large-AOI Tiled Building Benchmark" in summary
    assert "source profile snapshot" in summary
    assert "tile manifest" in summary
