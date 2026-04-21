from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

from adapters.poi_adapter import run_poi_fusion


def _write_shapefile(gdf: gpd.GeoDataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(path)
    return path


def test_run_poi_fusion_outputs_matched_osm_and_unmatched_ref_points(tmp_path: Path) -> None:
    osm = gpd.GeoDataFrame(
        {
            "name": ["osm clinic", "osm cafe"],
            "category": ["clinic", "cafe"],
        },
        geometry=[Point(0, 0), Point(1000, 1000)],
        crs="EPSG:3857",
    )
    ref = gpd.GeoDataFrame(
        {
            "name": ["ref clinic", "ref school"],
            "category": ["clinic", "school"],
        },
        geometry=[Point(10, 0), Point(2500, 2500)],
        crs="EPSG:3857",
    )
    osm_shp = _write_shapefile(osm, tmp_path / "osm" / "osm_poi.shp")
    ref_shp = _write_shapefile(ref, tmp_path / "ref" / "ref_poi.shp")

    output_shp = run_poi_fusion(
        osm_shp=osm_shp,
        ref_shp=ref_shp,
        output_dir=tmp_path / "output",
        target_crs="EPSG:3857",
    )

    assert output_shp.exists()
    assert output_shp.name == "fused_poi.shp"

    result = gpd.read_file(output_shp)
    assert result.crs.to_epsg() == 3857
    assert len(result) == 3
    assert list(result.columns) == [
        "POI_ID",
        "OSM_ID",
        "REF_ID",
        "MATCH_REF",
        "DIST_M",
        "SRC",
        "NAME",
        "CATEGORY",
        "geometry",
    ]
    assert result.geometry.notna().all()
    assert not result.geometry.is_empty.any()

    matched_osm = result.iloc[0]
    assert matched_osm["OSM_ID"] == 1
    assert matched_osm["REF_ID"] == 1
    assert matched_osm["MATCH_REF"] == 1
    assert matched_osm["DIST_M"] == pytest.approx(10.0)
    assert matched_osm["SRC"] == "osm"

    unmatched_osm = result.iloc[1]
    assert unmatched_osm["OSM_ID"] == 2
    assert unmatched_osm["REF_ID"] == 0
    assert unmatched_osm["MATCH_REF"] == 0

    unmatched_ref = result.iloc[2]
    assert unmatched_ref["OSM_ID"] == 0
    assert unmatched_ref["REF_ID"] == 2
    assert unmatched_ref["SRC"] == "ref"


def test_run_poi_fusion_preserves_mapped_source_ids(tmp_path: Path) -> None:
    osm = gpd.GeoDataFrame(
        {"osm_id": [11], "name": ["osm clinic"], "category": ["clinic"]},
        geometry=[Point(0, 0)],
        crs="EPSG:3857",
    )
    ref = gpd.GeoDataFrame(
        {"new_id": [101], "name": ["ref clinic"], "category": ["clinic"]},
        geometry=[Point(5, 0)],
        crs="EPSG:3857",
    )
    osm_shp = _write_shapefile(osm, tmp_path / "mapped-osm" / "osm_poi.shp")
    ref_shp = _write_shapefile(ref, tmp_path / "mapped-ref" / "ref_poi.shp")

    output_shp = run_poi_fusion(
        osm_shp=osm_shp,
        ref_shp=ref_shp,
        output_dir=tmp_path / "mapped-output",
        target_crs="EPSG:3857",
        field_mapping={
            "osm": {"OSM_ID": "osm_id"},
            "ref": {"REF_ID": "new_id"},
        },
    )

    result = gpd.read_file(output_shp)

    assert result.iloc[0]["OSM_ID"] == 11
    assert result.iloc[0]["REF_ID"] == 101
    assert result.iloc[0]["MATCH_REF"] == 101
