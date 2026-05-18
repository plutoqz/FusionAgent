from __future__ import annotations

from typing import Any

import geopandas as gpd
import pandas as pd

from fusion_algorithms.contracts import WaterLineFusionParams, WaterPolygonFusionParams
from fusion_algorithms.road_fusion import build_road_match_candidates, fuse_road_segments, split_features_in_gdf


def match_water_lines(
    base: gpd.GeoDataFrame,
    target: gpd.GeoDataFrame,
    params: WaterLineFusionParams | None = None,
) -> pd.DataFrame:
    return build_road_match_candidates(base, target, params or WaterLineFusionParams())


def fuse_water_lines(
    sources: dict[str, gpd.GeoDataFrame],
    params: WaterLineFusionParams | None = None,
) -> gpd.GeoDataFrame:
    params = params or WaterLineFusionParams()
    ordered = [name for name in params.line_priority_order if name in sources]
    if not ordered:
        raise ValueError("No water line sources available.")
    current = split_features_in_gdf(sources[ordered[0]], params)
    for name in ordered[1:]:
        current = fuse_road_segments(current, split_features_in_gdf(sources[name], params), params)
    return current


def match_water_polygons(
    base: gpd.GeoDataFrame,
    target: gpd.GeoDataFrame,
    params: WaterPolygonFusionParams | None = None,
) -> pd.DataFrame:
    params = params or WaterPolygonFusionParams()
    rows: list[dict[str, Any]] = []
    if base.empty or target.empty:
        return pd.DataFrame(columns=["base_index", "target_index", "overlap_ratio", "intersection_area"])
    target_sindex = target.sindex
    for base_pos, (_, base_row) in enumerate(base.iterrows()):
        geom = base_row.geometry
        area = max(float(geom.area), 1e-9)
        for target_pos in target_sindex.intersection(geom.bounds):
            target_geom = target.iloc[int(target_pos)].geometry
            if not geom.intersects(target_geom):
                continue
            inter_area = float(geom.intersection(target_geom).area)
            overlap_ratio = inter_area / area
            if overlap_ratio >= params.overlap_threshold and inter_area >= params.min_intersection_area:
                rows.append(
                    {
                        "base_index": base_pos,
                        "target_index": int(target_pos),
                        "overlap_ratio": overlap_ratio,
                        "intersection_area": inter_area,
                    }
                )
    return pd.DataFrame(rows)


def fuse_water_polygons(
    base: gpd.GeoDataFrame,
    target: gpd.GeoDataFrame,
    params: WaterPolygonFusionParams | None = None,
) -> gpd.GeoDataFrame:
    params = params or WaterPolygonFusionParams()
    matches = match_water_polygons(base, target, params)
    matched_targets = set(matches["target_index"].tolist()) if not matches.empty else set()
    rows = []
    if params.preserve_unmatched_osm:
        for _, row in base.iterrows():
            data = row.to_dict()
            data["SRC"] = "base"
            rows.append(data)
    if params.preserve_unmatched_new:
        for pos, (_, row) in enumerate(target.iterrows()):
            if pos in matched_targets:
                continue
            data = row.to_dict()
            data["SRC"] = "target"
            rows.append(data)
    if not rows:
        template = base if "geometry" in base.columns else target
        return template.iloc[0:0].copy()
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=base.crs or target.crs)
