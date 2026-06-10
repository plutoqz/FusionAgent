from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from agent.executor import ExecutionContext
from agent.tooling import build_default_tool_registry
from adapters.fusioncode_polygon_adapter import run_water_polygon_priority_merge
from schemas.fusion import JobType


def test_execution_context_carries_named_artifacts(tmp_path: Path) -> None:
    context = ExecutionContext(
        run_id="run-fusioncode",
        job_type=JobType.building,
        osm_shp=tmp_path / "osm.shp",
        ref_shp=tmp_path / "ref.shp",
        output_dir=tmp_path,
        target_crs="EPSG:4326",
        named_vectors={"MS": tmp_path / "ms.gpkg", "GG": tmp_path / "gg.gpkg"},
        named_rasters={"building_height": tmp_path / "height.vrt"},
        context_vectors={"roads": tmp_path / "roads.gpkg"},
    )
    assert context.named_vectors["MS"].name == "ms.gpkg"
    assert context.named_rasters["building_height"].name == "height.vrt"
    assert context.context_vectors["roads"].name == "roads.gpkg"


def test_tool_registry_exposes_fusioncode_handlers() -> None:
    registry = build_default_tool_registry()
    expected = {
        "algo.fusion.building.multi_source.decomposed.v1": "_handle_building_multi_source_decomposed",
        "algo.enrich.building.height_from_raster.v1": "_handle_building_height_from_raster",
        "algo.fusion.road.conflation.v7": "_handle_road_conflation_v7",
        "algo.fusion.waterways.conflation.v7": "_handle_waterways_conflation_v7",
        "algo.fusion.water_polygon.priority_merge.v2": "_handle_water_polygon_priority_merge",
        "algo.fusion.poi.geohash_neighbor_match.v1": "_handle_poi_geohash_neighbor_match",
    }
    for algorithm_id, handler_name in expected.items():
        assert registry.require(algorithm_id).handler_name == handler_name


def test_water_polygon_priority_merge_emits_standard_source_lineage(tmp_path: Path) -> None:
    base_path = tmp_path / "base.gpkg"
    target_path = tmp_path / "target.gpkg"
    gpd.GeoDataFrame(
        {"name": ["base-water"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:4326",
    ).to_file(base_path, driver="GPKG")
    gpd.GeoDataFrame(
        {"name": ["target-water"]},
        geometry=[Polygon([(2, 2), (2, 3), (3, 3), (3, 2)])],
        crs="EPSG:4326",
    ).to_file(target_path, driver="GPKG")
    context = ExecutionContext(
        run_id="run-water-lineage",
        job_type=JobType.water,
        osm_shp=base_path,
        ref_shp=target_path,
        output_dir=tmp_path / "output",
        target_crs="EPSG:4326",
        active_step=1,
    )

    output_path = run_water_polygon_priority_merge(context)

    result = gpd.read_file(output_path)
    assert set(result["source_id"]) == {"raw.osm.water", "raw.hydrolakes.water"}
