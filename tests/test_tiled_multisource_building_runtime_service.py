from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import box

from services.tile_partition_service import TileManifest, TileSpec
from services import tiled_building_runtime_service
from services.tiled_building_runtime_service import TiledBuildingRuntimeService


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
