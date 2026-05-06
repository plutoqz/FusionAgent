from __future__ import annotations

from typing import TYPE_CHECKING

import geopandas as gpd

from fusion_algorithms.contracts import RoadFusionParams, WaterLineFusionParams, params_from_mapping
from fusion_algorithms.road_fusion import run_road_segment_match_topology
from fusion_algorithms.water_fusion import fuse_water_lines

if TYPE_CHECKING:
    from agent.executor import ExecutionContext


def _write_gdf(gdf: gpd.GeoDataFrame, context: ExecutionContext, label: str):
    context.output_dir.mkdir(parents=True, exist_ok=True)
    step = context.active_step if context.active_step is not None else 0
    path = context.output_dir / f"step_{step:02d}_{label}.gpkg"
    gdf.to_file(path, driver="GPKG")
    return path


def _read_pair(context: ExecutionContext) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    base = gpd.read_file(context.osm_shp)
    target = gpd.read_file(context.ref_shp)
    if base.crs is None:
        base = base.set_crs(context.target_crs)
    if target.crs is None:
        target = target.set_crs(context.target_crs)
    return base.to_crs(context.target_crs), target.to_crs(context.target_crs)


def run_road_segment_topology(context: ExecutionContext):
    base, target = _read_pair(context)
    params = params_from_mapping(RoadFusionParams, context.step_parameters)
    return _write_gdf(run_road_segment_match_topology(base, target, params), context, "road_segment_match_topology")


def run_water_line_three_source(context: ExecutionContext):
    sources = {}
    if context.named_vectors:
        for name, path in context.named_vectors.items():
            frame = gpd.read_file(path)
            if frame.crs is None:
                frame = frame.set_crs(context.target_crs)
            sources[name.upper()] = frame.to_crs(context.target_crs)
    else:
        base, target = _read_pair(context)
        sources = {"OSM": base, "MS": target}
    params = params_from_mapping(WaterLineFusionParams, context.step_parameters)
    return _write_gdf(fuse_water_lines(sources, params), context, "water_line_three_source")
