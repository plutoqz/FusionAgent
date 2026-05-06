from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import geopandas as gpd
import pandas as pd

from fusion_algorithms.contracts import BuildingMatchParams, SourceSpec, dataclass_to_dict
from fusion_algorithms.fusioncode_loader import load_module


@dataclass(frozen=True)
class CandidateGraph:
    edges: pd.DataFrame
    base: gpd.GeoDataFrame
    target: gpd.GeoDataFrame
    roads: gpd.GeoDataFrame | None
    base_name: str
    target_name: str
    params: BuildingMatchParams


@dataclass(frozen=True)
class ComponentSolution:
    groups: list[dict]
    graph: CandidateGraph


def to_match_config(params: BuildingMatchParams | None = None):
    params = params or BuildingMatchParams()
    module = load_module("matching_engine")
    cfg = module.MatchConfig()
    values = dataclass_to_dict(params)
    for key, value in values.items():
        if key in {"extra", "source_priority_order"}:
            continue
        if value is not None and hasattr(cfg, key):
            setattr(cfg, key, value)
    if params.workers is not None and hasattr(cfg, "workers"):
        cfg.workers = int(params.workers)
    return cfg


def _prepare_for_v8(gdf: gpd.GeoDataFrame, prefix: str) -> gpd.GeoDataFrame:
    module = load_module("matching_engine")
    prepared = gdf.copy()
    prepared["geometry"] = prepared.geometry.apply(module.safe_make_valid)
    prepared = prepared[prepared.geometry.notnull()].reset_index(drop=True)
    feature_df = module.extract_base_features(prepared, prefix)
    return pd.concat([prepared, feature_df], axis=1)


def normalize_building_sources(
    source_specs: list[SourceSpec],
    target_crs: str,
    min_area: float = 0.0,
) -> dict[str, gpd.GeoDataFrame]:
    normalized: dict[str, gpd.GeoDataFrame] = {}
    for spec in sorted(source_specs, key=lambda item: item.priority):
        frame = gpd.read_file(Path(spec.path))
        if frame.crs is None:
            frame = frame.set_crs(target_crs)
        frame = frame.to_crs(target_crs)
        frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
        if min_area > 0:
            frame = frame[frame.geometry.area >= min_area].copy()
        frame["source_name"] = spec.name
        normalized[spec.name] = frame.reset_index(drop=True)
    return normalized


def build_v8_candidate_graph(
    base_gdf: gpd.GeoDataFrame,
    target_gdf: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame | None,
    params: BuildingMatchParams | None = None,
    *,
    base_name: str = "Base",
    target_name: str = "Target",
) -> CandidateGraph:
    params = params or BuildingMatchParams()
    module = load_module("matching_engine")
    cfg = to_match_config(params)
    base = _prepare_for_v8(base_gdf, "g")
    target = _prepare_for_v8(target_gdf, "m")
    edges, _ = module.generate_candidate_edges_v8(base, target, roads, cfg)
    return CandidateGraph(
        edges=edges,
        base=base,
        target=target,
        roads=roads,
        base_name=base_name,
        target_name=target_name,
        params=params,
    )


def solve_v8_components(candidate_graph: CandidateGraph) -> ComponentSolution:
    module = load_module("matching_engine")
    cfg = to_match_config(candidate_graph.params)
    if candidate_graph.edges.empty:
        return ComponentSolution(groups=[], graph=candidate_graph)

    base_features = candidate_graph.base.set_index("g_id")
    target_features = candidate_graph.target.set_index("m_id")
    g_nodes = base_features[["area", "quality", "cx", "cy", "minx", "miny", "maxx", "maxy"]].to_dict("index")
    m_nodes = target_features[["area", "quality", "cx", "cy", "minx", "miny", "maxx", "maxy"]].to_dict("index")
    payload = (
        candidate_graph.edges.to_dict("records"),
        {int(k): v for k, v in g_nodes.items()},
        {int(k): v for k, v in m_nodes.items()},
        cfg,
    )
    return ComponentSolution(groups=module.process_worker_v8(payload), graph=candidate_graph)


def build_cascade_fusion_rows(solution: ComponentSolution) -> gpd.GeoDataFrame:
    graph = solution.graph
    module = load_module("matching_engine")
    cfg = to_match_config(graph.params)
    base_geom_dict = graph.base.set_index("g_id")["geometry"].to_dict()
    target_geom_dict = graph.target.set_index("m_id")["geometry"].to_dict()
    fusion_rows, matched_base, matched_target = module.build_fusion_rows(
        solution.groups,
        graph.base,
        graph.target,
        base_geom_dict,
        target_geom_dict,
        cfg,
        graph.base_name,
        graph.target_name,
    )
    fusion_rows = module.append_unmatched_rows(
        fusion_rows,
        matched_base,
        matched_target,
        graph.base,
        graph.target,
        base_geom_dict,
        target_geom_dict,
        cfg,
        graph.base_name,
        graph.target_name,
    )
    return gpd.GeoDataFrame(fusion_rows, geometry="geometry", crs=graph.base.crs)


def resolve_residual_priority_conflicts(
    fusion_rows: gpd.GeoDataFrame,
    params: BuildingMatchParams | None = None,
    *,
    base_name: str = "Base",
    target_name: str = "Target",
) -> gpd.GeoDataFrame:
    module = load_module("matching_engine")
    cfg = to_match_config(params or BuildingMatchParams())
    rows = module.resolve_residual_conflicts_by_priority(
        fusion_rows.to_dict("records"),
        cfg,
        base_name,
        target_name,
    )
    rows = [row for row in rows if int(row.get("suppress_flag", 0)) == 0]
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=fusion_rows.crs)


def run_pairwise_v8_fusion(
    base_gdf: gpd.GeoDataFrame,
    target_gdf: gpd.GeoDataFrame,
    roads: gpd.GeoDataFrame | None,
    params: BuildingMatchParams | None = None,
    *,
    base_name: str = "Base",
    target_name: str = "Target",
) -> gpd.GeoDataFrame:
    module = load_module("matching_engine")
    cfg = to_match_config(params or BuildingMatchParams())
    fused = module.execute_v8_fusion(base_gdf, target_gdf, roads, cfg, base_name=base_name, target_name=target_name)
    if "fusion_lineage" not in fused.columns:
        fused["fusion_lineage"] = f"{base_name}+{target_name}"
    return fused


def run_cascaded_multi_source_fusion(
    source_map: Mapping[str, gpd.GeoDataFrame],
    roads: gpd.GeoDataFrame | None,
    params: BuildingMatchParams | None = None,
    source_priority_order: tuple[str, ...] | None = None,
) -> gpd.GeoDataFrame:
    params = params or BuildingMatchParams()
    order = tuple(source_priority_order or params.source_priority_order)
    available = [name for name in order if name in source_map]
    if not available:
        raise ValueError("No building sources available for cascaded fusion.")
    current = source_map[available[0]].copy()
    current_name = available[0]
    for next_name in available[1:]:
        current = run_pairwise_v8_fusion(
            current,
            source_map[next_name],
            roads,
            params,
            base_name=current_name,
            target_name=next_name,
        )
        current_name = f"FUSED_{current_name}_{next_name}"
    return current
