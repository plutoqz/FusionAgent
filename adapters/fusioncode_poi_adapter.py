from __future__ import annotations

from typing import TYPE_CHECKING

import geopandas as gpd

from fusion_algorithms.contracts import PoiFusionParams, params_from_mapping
from fusion_algorithms.poi_fusion import run_poi_geohash_priority_fusion
from services.runtime_source_aliases import POI_SOURCE_PRIORITY_ORDER

if TYPE_CHECKING:
    from agent.executor import ExecutionContext


DEFAULT_POI_SOURCE_PRIORITY_ORDER = POI_SOURCE_PRIORITY_ORDER


def run_poi_geohash_neighbor_match(context: ExecutionContext):
    sources = {}
    if context.named_vectors:
        raw_items = {str(name).upper(): path for name, path in context.named_vectors.items()}
        ordered_names = [name for name in DEFAULT_POI_SOURCE_PRIORITY_ORDER if name in raw_items]
        ordered_names.extend(sorted(name for name in raw_items if name not in DEFAULT_POI_SOURCE_PRIORITY_ORDER))
        for name in ordered_names:
            path = raw_items[name]
            frame = gpd.read_file(path)
            if frame.crs is None:
                frame = frame.set_crs(context.target_crs)
            sources[name] = frame.to_crs(context.target_crs)
    else:
        base = gpd.read_file(context.osm_shp)
        target = gpd.read_file(context.ref_shp)
        if base.crs is None:
            base = base.set_crs(context.target_crs)
        if target.crs is None:
            target = target.set_crs(context.target_crs)
        sources = {"OSM": base.to_crs(context.target_crs), "GNG": target.to_crs(context.target_crs)}
    step_parameters = dict(context.step_parameters or {})
    if "source_priority_order" not in step_parameters:
        step_parameters["source_priority_order"] = DEFAULT_POI_SOURCE_PRIORITY_ORDER
    params = params_from_mapping(PoiFusionParams, step_parameters)
    output = run_poi_geohash_priority_fusion(sources, params)
    context.output_dir.mkdir(parents=True, exist_ok=True)
    step = context.active_step if context.active_step is not None else 0
    path = context.output_dir / f"step_{step:02d}_poi_geohash_neighbor_match.gpkg"
    output.to_file(path, driver="GPKG")
    return path
