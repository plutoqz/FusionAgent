from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString

from adapters.road_adapter import run_road_fusion


def _write_shapefile(gdf: gpd.GeoDataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path)
    return path


def test_run_road_fusion_preserves_target_crs_and_basic_schema(tmp_path: Path) -> None:
    osm = gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["primary"], "name": ["OSM Road"]},
        geometry=[LineString([(0, 0), (100, 0)])],
        crs="EPSG:3857",
    )
    ref = gpd.GeoDataFrame(
        {"FID_1": [11], "name": ["Reference Road"]},
        geometry=[LineString([(0, 1), (100, 1)])],
        crs="EPSG:3857",
    )
    osm_shp = _write_shapefile(osm, tmp_path / "osm" / "roads.shp")
    ref_shp = _write_shapefile(ref, tmp_path / "ref" / "roads.shp")

    output_shp = run_road_fusion(
        osm_shp=osm_shp,
        ref_shp=ref_shp,
        output_dir=tmp_path / "output",
        target_crs="EPSG:3857",
        parameters={"dedupe_buffer_m": 1.0},
    )

    result = gpd.read_file(output_shp)
    assert output_shp.name == "fused_roads.shp"
    assert result.crs.to_epsg() == 3857
    assert len(result) >= 1
    assert "osm_id" in result.columns or "OSM_ID" in result.columns
    assert result.geometry.notna().all()
    assert not result.geometry.is_empty.any()
