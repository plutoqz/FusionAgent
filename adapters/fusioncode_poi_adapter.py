from __future__ import annotations

from typing import TYPE_CHECKING

import geopandas as gpd

from fusion_algorithms.contracts import PoiFusionParams, params_from_mapping
from fusion_algorithms.poi_fusion import run_poi_geohash_priority_fusion

if TYPE_CHECKING:
    from agent.executor import ExecutionContext


def run_poi_geohash_neighbor_match(context: ExecutionContext):
    sources = {}
    if context.named_vectors:
        for name, path in context.named_vectors.items():
            frame = gpd.read_file(path)
            if frame.crs is None:
                frame = frame.set_crs(context.target_crs)
            sources[name.upper()] = frame.to_crs(context.target_crs)
    else:
        base = gpd.read_file(context.osm_shp)
        target = gpd.read_file(context.ref_shp)
        if base.crs is None:
            base = base.set_crs(context.target_crs)
        if target.crs is None:
            target = target.set_crs(context.target_crs)
        sources = {"OSM": base.to_crs(context.target_crs), "GNG": target.to_crs(context.target_crs)}
    params = params_from_mapping(PoiFusionParams, context.step_parameters)
    output = run_poi_geohash_priority_fusion(sources, params)
    context.output_dir.mkdir(parents=True, exist_ok=True)
    step = context.active_step if context.active_step is not None else 0
    path = context.output_dir / f"step_{step:02d}_poi_geohash_neighbor_match.gpkg"
    output.to_file(path, driver="GPKG")
    return path
