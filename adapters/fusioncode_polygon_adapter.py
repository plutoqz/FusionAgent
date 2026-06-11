from __future__ import annotations

from typing import TYPE_CHECKING

import geopandas as gpd

from fusion_algorithms.contracts import WaterPolygonFusionParams, params_from_mapping
from fusion_algorithms.water_fusion import fuse_water_polygons

if TYPE_CHECKING:
    from agent.executor import ExecutionContext


def run_water_polygon_priority_merge(context: ExecutionContext):
    base = gpd.read_file(context.osm_shp)
    target = gpd.read_file(context.ref_shp)
    if base.crs is None:
        base = base.set_crs(context.target_crs)
    if target.crs is None:
        target = target.set_crs(context.target_crs)
    params = params_from_mapping(WaterPolygonFusionParams, context.step_parameters)
    output = fuse_water_polygons(base.to_crs(context.target_crs), target.to_crs(context.target_crs), params)
    if "source_id" not in output.columns and "SRC" in output.columns:
        output["source_id"] = output["SRC"].replace(
            {
                "base": "raw.osm.water",
                "target": "raw.hydrolakes.water",
            }
        )
    context.output_dir.mkdir(parents=True, exist_ok=True)
    step = context.active_step if context.active_step is not None else 0
    path = context.output_dir / f"step_{step:02d}_water_polygon_priority_merge.gpkg"
    output.to_file(path, driver="GPKG")
    return path
