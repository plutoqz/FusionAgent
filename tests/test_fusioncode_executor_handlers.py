from __future__ import annotations

from pathlib import Path

from agent.executor import ExecutionContext
from agent.tooling import build_default_tool_registry
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
        "algo.fusion.road.segment_match_topology.v1": "_handle_road_segment_match_topology",
        "algo.fusion.water.polygon_priority_merge.v1": "_handle_water_polygon_priority_merge",
        "algo.fusion.poi.geohash_neighbor_match.v1": "_handle_poi_geohash_neighbor_match",
    }
    for algorithm_id, handler_name in expected.items():
        assert registry.require(algorithm_id).handler_name == handler_name
