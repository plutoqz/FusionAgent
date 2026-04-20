from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import box

from adapters.water_adapter import run_water_fusion


def _write_shapefile(gdf: gpd.GeoDataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path)
    return path


def test_run_water_fusion_outputs_matched_osm_and_unmatched_ref_polygons(tmp_path: Path) -> None:
    osm = gpd.GeoDataFrame(
        {
            "name": ["osm lake", "isolated pond"],
            "fclass": ["water", "reservoir"],
            "water_ty": ["lake", "pond"],
        },
        geometry=[box(0, 0, 10, 10), box(30, 30, 40, 40)],
        crs="EPSG:3857",
    )
    ref = gpd.GeoDataFrame(
        {
            "name": ["ref lake", "new wetland"],
            "fclass": ["water", "wetland"],
            "water_ty": ["lake", "wetland"],
        },
        geometry=[box(1, 1, 9, 9), box(60, 60, 70, 70)],
        crs="EPSG:3857",
    )
    osm_shp = _write_shapefile(osm, tmp_path / "osm" / "osm_water.shp")
    ref_shp = _write_shapefile(ref, tmp_path / "ref" / "ref_water.shp")

    output_shp = run_water_fusion(
        osm_shp=osm_shp,
        ref_shp=ref_shp,
        output_dir=tmp_path / "output",
        target_crs="EPSG:3857",
    )

    assert output_shp.exists()
    assert output_shp.name == "fused_water.shp"

    result = gpd.read_file(output_shp)
    assert result.crs.to_epsg() == 3857
    assert len(result) == 3
    assert list(result.columns) == [
        "OSM_ID",
        "REF_ID",
        "MATCH_REF",
        "OV_RATIO",
        "MATCH_CNT",
        "SRC",
        "NAME",
        "FCLASS",
        "WATER_TY",
        "geometry",
    ]
    assert result.geometry.notna().all()
    assert not result.geometry.is_empty.any()

    first_osm = result.iloc[0]
    assert first_osm["OSM_ID"] == 1
    assert first_osm["REF_ID"] == 1
    assert first_osm["MATCH_REF"] == 1
    assert first_osm["OV_RATIO"] == pytest.approx(0.64)
    assert first_osm["MATCH_CNT"] == 1

    second_osm = result.iloc[1]
    assert second_osm["OSM_ID"] == 2
    assert second_osm["REF_ID"] == 0
    assert second_osm["MATCH_REF"] == 0
    assert second_osm["MATCH_CNT"] == 0

    unmatched_ref = result.iloc[2]
    assert unmatched_ref["OSM_ID"] == 0
    assert unmatched_ref["REF_ID"] == 2
    assert unmatched_ref["SRC"] == "ref"
