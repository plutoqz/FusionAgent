from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from services.tile_partition_service import TileManifest, TileSpec
from services import tiled_building_runtime_service
from services.tiled_building_runtime_service import MultiSourceTileRunArtifact, TiledBuildingRuntimeService


def _write_source(path: Path, *, height: float, field: str = "height") -> None:
    frame = gpd.GeoDataFrame(
        {field: [height]},
        geometry=[box(0.2, 0.2, 0.8, 0.8)],
        crs="EPSG:3857",
    )
    frame.to_file(path, driver="GPKG")


def _single_tile_manifest() -> TileManifest:
    return TileManifest(
        bbox=(0.0, 0.0, 1.0, 1.0),
        bbox_crs="EPSG:3857",
        working_crs="EPSG:3857",
        tile_width_m=1.0,
        tile_height_m=1.0,
        overlap_m=0.1,
        tiles=[
            TileSpec(
                tile_id="tile_000_000",
                bbox=(0.0, 0.0, 1.0, 1.0),
                buffered_bbox=(-0.1, -0.1, 1.1, 1.1),
                working_bbox=(0.0, 0.0, 1.0, 1.0),
                working_buffered_bbox=(-0.1, -0.1, 1.1, 1.1),
                row=0,
                col=0,
            )
        ],
    )


def test_tiled_multisource_runtime_runs_all_sources_and_writes_height_gpkg(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ms_path = tmp_path / "ms.gpkg"
    obm_path = tmp_path / "obm.gpkg"
    gg_path = tmp_path / "gg.gpkg"
    _write_source(ms_path, height=4.0)
    _write_source(obm_path, height=9.0)
    _write_source(gg_path, height=3.0, field="Height")
    calls = []

    def fake_multisource(source_map, roads, params, source_priority_order):
        del roads, params
        calls.append(tuple(source_priority_order))
        assert tuple(source_map) == ("MS", "OBM", "GG")
        return gpd.GeoDataFrame(
            {"height_fused": [4.0]},
            geometry=[box(0.2, 0.2, 0.8, 0.8)],
            crs="EPSG:3857",
        )

    monkeypatch.setattr(
        tiled_building_runtime_service,
        "run_cascaded_multi_source_fusion",
        fake_multisource,
    )
    result = TiledBuildingRuntimeService(max_workers=1).run_tiled_multisource_building_job(
        run_id="run-multisource",
        tile_manifest=_single_tile_manifest(),
        vector_sources={"MS": ms_path, "OBM": obm_path, "GG": gg_path},
        output_dir=tmp_path / "out",
        target_crs="EPSG:3857",
        source_priority_order=("MS", "OBM", "GG"),
    )

    assert calls == [("MS", "OBM", "GG")]
    assert result.output_path.suffix == ".gpkg"
    output = gpd.read_file(result.output_path)
    assert len(output) == 1
    assert float(output.loc[0, "height_ms"]) == 4.0
    assert float(output.loc[0, "height_obm"]) == 9.0
    assert float(output.loc[0, "height_google"]) == 3.0
    assert float(output.loc[0, "height_final"]) == 9.0
    assert output.loc[0, "height_final_source"] == "height_obm"


def test_tiled_multisource_runtime_prefers_positive_height_raster_when_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ms_path = tmp_path / "ms.gpkg"
    osm_path = tmp_path / "osm.gpkg"
    height_path = tmp_path / "height.tif"
    _write_source(ms_path, height=4.0)
    _write_source(osm_path, height=3.0)
    height_path.write_bytes(b"fake-raster")

    def fake_multisource(source_map, roads, params, source_priority_order):
        del roads, params, source_priority_order
        frame = next(iter(source_map.values())).copy()
        frame["height_fused"] = 4.0
        return frame

    def fake_enrich(frame, raster, params):
        del raster, params
        enriched = frame.copy()
        enriched["height_raster"] = 15.0
        enriched["height_final"] = 15.0
        enriched["height_final_source"] = "raster"
        return enriched

    monkeypatch.setattr(
        tiled_building_runtime_service,
        "run_cascaded_multi_source_fusion",
        fake_multisource,
    )
    monkeypatch.setattr(tiled_building_runtime_service, "enrich_height_from_raster", fake_enrich)

    result = TiledBuildingRuntimeService(max_workers=1).run_tiled_multisource_building_job(
        run_id="run-multisource-height",
        tile_manifest=_single_tile_manifest(),
        vector_sources={"MS": ms_path, "OSM": osm_path},
        raster_sources={"building_height": height_path},
        output_dir=tmp_path / "out-height",
        target_crs="EPSG:3857",
        source_priority_order=("MS", "OSM"),
    )

    output = gpd.read_file(result.output_path)
    assert "height_raster" in output.columns
    assert float(output.loc[0, "height_final"]) == 15.0
    assert output.loc[0, "height_final_source"] == "raster"


def test_tiled_multisource_runtime_uses_bounded_priority_fallback_for_large_tile(
    tmp_path: Path,
    monkeypatch,
) -> None:
    ms_path = tmp_path / "ms.gpkg"
    osm_path = tmp_path / "osm.gpkg"
    _write_source(ms_path, height=4.0)
    _write_source(osm_path, height=3.0)

    def fail_multisource(*_args, **_kwargs):
        raise AssertionError("V8 matching should be skipped for bounded large-tile fallback")

    monkeypatch.setattr(
        tiled_building_runtime_service,
        "run_cascaded_multi_source_fusion",
        fail_multisource,
    )

    def fail_height_attachment(*_args, **_kwargs):
        raise AssertionError("bounded fallback should not intersect secondary sources for height attachment")

    monkeypatch.setattr(
        tiled_building_runtime_service,
        "attach_source_heights_and_final",
        fail_height_attachment,
    )

    result = TiledBuildingRuntimeService(max_workers=1).run_tiled_multisource_building_job(
        run_id="run-bounded-fallback",
        tile_manifest=_single_tile_manifest(),
        vector_sources={"MS": ms_path, "OSM": osm_path},
        output_dir=tmp_path / "out-bounded",
        target_crs="EPSG:3857",
        source_priority_order=("MS", "OSM"),
        parameters={"large_tile_fallback_feature_threshold": 1},
    )

    output = gpd.read_file(result.output_path)
    assert len(output) == 1
    assert output.loc[0, "fusion_runtime_mode"] == "bounded_priority_tile"
    assert output.loc[0, "fusion_source"] == "MS"
    assert float(output.loc[0, "height_ms"]) == 4.0
    assert float(output.loc[0, "height_final"]) == 4.0


def test_stitch_multisource_tile_outputs_streams_without_concat(tmp_path: Path, monkeypatch) -> None:
    output_dir = tmp_path / "tiles"
    output_dir.mkdir(parents=True, exist_ok=True)
    tile_a = output_dir / "tile_a.gpkg"
    tile_b = output_dir / "tile_b.gpkg"
    gpd.GeoDataFrame(
        {"fusion_source": ["MS"]},
        geometry=[box(0.1, 0.1, 0.4, 0.4)],
        crs="EPSG:3857",
    ).to_file(tile_a, driver="GPKG")
    gpd.GeoDataFrame(
        {"fusion_source": ["MS"]},
        geometry=[box(1.1, 0.1, 1.4, 0.4)],
        crs="EPSG:3857",
    ).to_file(tile_b, driver="GPKG")

    def fail_concat(*_args, **_kwargs):
        raise AssertionError("streaming stitch should not concatenate all tile frames")

    monkeypatch.setattr(pd, "concat", fail_concat)

    result = TiledBuildingRuntimeService(max_workers=1)._stitch_multisource_tile_outputs(
        tile_results=[
            MultiSourceTileRunArtifact(
                tile_id="tile_000_000",
                output_path=tile_a,
                feature_count=1,
                bbox=(0.0, 0.0, 1.0, 1.0),
                buffered_bbox=(0.0, 0.0, 1.0, 1.0),
                working_bbox=(0.0, 0.0, 1.0, 1.0),
                working_buffered_bbox=(0.0, 0.0, 1.0, 1.0),
            ),
            MultiSourceTileRunArtifact(
                tile_id="tile_000_001",
                output_path=tile_b,
                feature_count=1,
                bbox=(1.0, 0.0, 2.0, 1.0),
                buffered_bbox=(1.0, 0.0, 2.0, 1.0),
                working_bbox=(1.0, 0.0, 2.0, 1.0),
                working_buffered_bbox=(1.0, 0.0, 2.0, 1.0),
            ),
        ],
        output_path=tmp_path / "stitched.gpkg",
        target_crs="EPSG:3857",
    )

    stitched = gpd.read_file(result)
    assert len(stitched) == 2
