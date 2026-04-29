from __future__ import annotations

from typing import Any

import geopandas as gpd

from fusion_algorithms.contracts import BuildingOptimizationParams, dataclass_to_dict
from fusion_algorithms.fusioncode_loader import load_module, load_optional_module


def to_opt_config(params: BuildingOptimizationParams | None = None):
    params = params or BuildingOptimizationParams()
    module = load_module("spatial_optimizer")
    cfg = module.OptConfig()
    for key, value in dataclass_to_dict(params).items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    return cfg


def _apply_global_config(module: Any, params: BuildingOptimizationParams):
    cfg = to_opt_config(params)
    if hasattr(module, "CONFIG"):
        module.CONFIG = cfg
    return cfg


def optimize_building_road_topology(
    buildings: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame | None,
    params: BuildingOptimizationParams | None = None,
) -> gpd.GeoDataFrame:
    if roads is None or roads.empty:
        return buildings.copy()
    module = load_module("spatial_optimizer")
    _apply_global_config(module, params or BuildingOptimizationParams())
    return module.optimize_road_topology(roads, buildings.copy())


def optimize_building_conflict_graph(
    buildings: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame | None,
    params: BuildingOptimizationParams | None = None,
) -> gpd.GeoDataFrame:
    module = load_module("spatial_optimizer")
    _apply_global_config(module, params or BuildingOptimizationParams())
    result = module.run_graph_optimization_v5(buildings.copy(), road_gdf=roads, silent=True)
    if isinstance(result, tuple):
        return result[0]
    return result


def refine_post_conflict_shrink(
    buildings: gpd.GeoDataFrame,
    params: BuildingOptimizationParams | None = None,
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    params = params or BuildingOptimizationParams()
    module = load_optional_module("post_conflict_shrink_refiner")
    if module is None or not params.enable_post_conflict_shrink:
        return buildings.copy(), {"enabled": False, "reason": "not_available_or_disabled"}
    return module.run_post_conflict_shrink_refinement(
        buildings.copy(),
        params.post_shrink_threshold_m2,
        params.post_shrink_scale_cap_pct,
        params.post_shrink_scale_step_pct,
        silent=True,
    )


def refine_road_tail_conflicts(
    buildings: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame | None,
    params: BuildingOptimizationParams | None = None,
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    params = params or BuildingOptimizationParams()
    if roads is None or roads.empty:
        return buildings.copy(), {"enabled": False, "reason": "missing_roads"}
    module = load_optional_module("z1r3_conflict")
    if module is None:
        return buildings.copy(), {"enabled": False, "reason": "not_available"}
    return module.road_tail_refinement(buildings.copy(), roads, silent=True)


def assess_building_quality(
    before: gpd.GeoDataFrame,
    after: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame | None,
    params: BuildingOptimizationParams | None = None,
) -> dict[str, Any]:
    del params
    module = load_module("spatial_optimizer")
    try:
        return module.calculate_metrics(before, after, gdf_road=roads, silent=True, return_pair_details=True)
    except TypeError:
        return module.calculate_metrics(before, after, road_gdf=roads, silent=True, return_pair_details=True)


def run_building_optimization_chain(
    raw_fused: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame | None,
    params: BuildingOptimizationParams | None = None,
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    params = params or BuildingOptimizationParams()
    lineage: dict[str, Any] = {}
    baseline = raw_fused.copy()
    road_adjusted = optimize_building_road_topology(raw_fused, roads, params)
    lineage["road_topology"] = {"enabled": roads is not None and not roads.empty}
    optimized = optimize_building_conflict_graph(road_adjusted, roads, params)
    lineage["conflict_graph"] = {"enabled": True}
    refined, shrink_summary = refine_post_conflict_shrink(optimized, params)
    lineage["post_conflict_shrink"] = shrink_summary
    tailed, tail_summary = refine_road_tail_conflicts(refined, roads, params)
    lineage["road_tail"] = tail_summary
    lineage["quality"] = assess_building_quality(baseline, tailed, roads, params)
    return tailed, lineage
