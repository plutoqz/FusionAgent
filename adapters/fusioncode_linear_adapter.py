from __future__ import annotations

from dataclasses import fields
from typing import TYPE_CHECKING

import geopandas as gpd

from fusion_algorithms.road_conflation_v7 import RoadConflationV7Config, run_road_conflation_v7 as _run_road_v7
from fusion_algorithms.waterways_conflation_v7 import (
    WaterwaysConflationV7Config,
    run_waterways_conflation_v7 as _run_waterways_v7,
)

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


def _config_from_mapping(config_cls, values: dict | None):
    allowed = {item.name for item in fields(config_cls)}
    return config_cls(**{key: value for key, value in dict(values or {}).items() if key in allowed})


def run_road_conflation_v7(context: ExecutionContext):
    base, target = _read_pair(context)
    config = _config_from_mapping(RoadConflationV7Config, context.step_parameters)
    result = _run_road_v7(base, target, config=config)
    return _write_gdf(result.frame, context, "road_conflation_v7")


def run_waterways_conflation_v7(context: ExecutionContext):
    base, target = _read_pair(context)
    config = _config_from_mapping(WaterwaysConflationV7Config, context.step_parameters)
    result = _run_waterways_v7(base, target, config=config)
    return _write_gdf(result.frame, context, "waterways_conflation_v7")


def run_road_segment_topology(context: ExecutionContext):
    return run_road_conflation_v7(context)


def run_water_line_three_source(context: ExecutionContext):
    return run_waterways_conflation_v7(context)
