from __future__ import annotations

import math
from typing import Any

import geopandas as gpd
import pandas as pd
from scipy.spatial.distance import directed_hausdorff
from shapely.geometry import LineString, MultiLineString, Point
from shapely.ops import linemerge, unary_union

from fusion_algorithms.contracts import RoadFusionParams


def calculate_angle(p1: tuple[float, float], p2: tuple[float, float], p3: tuple[float, float]) -> float:
    a = (p1[0] - p2[0], p1[1] - p2[1])
    b = (p3[0] - p2[0], p3[1] - p2[1])
    mag_a = math.hypot(*a)
    mag_b = math.hypot(*b)
    if mag_a == 0 or mag_b == 0:
        return 180.0
    cos_theta = (a[0] * b[0] + a[1] * b[1]) / (mag_a * mag_b)
    return math.degrees(math.acos(max(min(cos_theta, 1.0), -1.0)))


def split_at_sharp_turns(line, angle_threshold: float) -> list[LineString]:
    if isinstance(line, MultiLineString):
        parts: list[LineString] = []
        for part in line.geoms:
            parts.extend(split_at_sharp_turns(part, angle_threshold))
        return parts
    if not isinstance(line, LineString):
        return []
    coords = list(line.coords)
    if len(coords) <= 2:
        return [line]
    split_indices = [0]
    for idx in range(1, len(coords) - 1):
        if calculate_angle(coords[idx - 1], coords[idx], coords[idx + 1]) < angle_threshold:
            split_indices.append(idx)
    split_indices.append(len(coords) - 1)
    parts = []
    for start, end in zip(split_indices, split_indices[1:]):
        if end > start:
            parts.append(LineString(coords[start : end + 1]))
    return parts or [line]


def split_features_in_gdf(gdf: gpd.GeoDataFrame, params: RoadFusionParams) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf.iloc[0:0].copy()
    rows: list[dict[str, Any]] = []
    for _, row in gdf.iterrows():
        for part in split_at_sharp_turns(row.geometry, params.angle_threshold_deg):
            data = row.drop(labels=["geometry"]).to_dict()
            data["geometry"] = part
            rows.append(data)
    if not rows:
        return gdf.iloc[0:0].copy()
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=gdf.crs)


def line_angle(line) -> float:
    if isinstance(line, MultiLineString):
        line = max(line.geoms, key=lambda part: part.length)
    coords = list(line.coords)
    if len(coords) < 2:
        return 0.0
    dx = coords[-1][0] - coords[0][0]
    dy = coords[-1][1] - coords[0][1]
    return math.degrees(math.atan2(dy, dx)) % 180


def hausdorff_distance(line1, line2) -> float:
    coords1 = list(line1.coords)
    coords2 = list(line2.coords)
    if not coords1 or not coords2:
        return float("inf")
    return float(max(directed_hausdorff(coords1, coords2)[0], directed_hausdorff(coords2, coords1)[0]))


def build_road_match_candidates(
    base: gpd.GeoDataFrame,
    target: gpd.GeoDataFrame,
    params: RoadFusionParams | None = None,
) -> pd.DataFrame:
    params = params or RoadFusionParams()
    rows: list[dict[str, Any]] = []
    if base.empty or target.empty:
        return pd.DataFrame(columns=["base_index", "target_index", "hausdorff_m", "angle_diff_deg", "length_similarity"])
    target_sindex = target.sindex
    for base_pos, (_, base_row) in enumerate(base.iterrows()):
        base_geom = base_row.geometry
        for target_pos in target_sindex.intersection(base_geom.buffer(params.buffer_dist_m).bounds):
            target_geom = target.iloc[int(target_pos)].geometry
            if not base_geom.buffer(params.buffer_dist_m).intersects(target_geom):
                continue
            hd = hausdorff_distance(base_geom, target_geom)
            angle_diff = abs(line_angle(base_geom) - line_angle(target_geom)) % 180
            angle_diff = min(angle_diff, 180 - angle_diff)
            length_similarity = min(base_geom.length, target_geom.length) / max(base_geom.length, target_geom.length, 1e-9)
            if (
                hd <= params.max_hausdorff_m
                and angle_diff <= params.angle_diff_max_deg
                and length_similarity >= params.min_length_similarity
            ):
                rows.append(
                    {
                        "base_index": base_pos,
                        "target_index": int(target_pos),
                        "hausdorff_m": hd,
                        "angle_diff_deg": angle_diff,
                        "length_similarity": length_similarity,
                    }
                )
    return pd.DataFrame(rows)


def fuse_road_segments(
    base: gpd.GeoDataFrame,
    target: gpd.GeoDataFrame,
    params: RoadFusionParams | None = None,
) -> gpd.GeoDataFrame:
    params = params or RoadFusionParams()
    candidates = build_road_match_candidates(base, target, params)
    used_target = set(candidates.sort_values(["hausdorff_m", "angle_diff_deg"]).drop_duplicates("base_index")["target_index"])
    rows = []
    for _, row in base.iterrows():
        data = row.to_dict()
        data["SRC"] = "base"
        rows.append(data)
    for pos, (_, row) in enumerate(target.iterrows()):
        if pos in used_target:
            continue
        data = row.to_dict()
        data["SRC"] = "target"
        rows.append(data)
    if not rows:
        template = base if "geometry" in base.columns else target
        return template.iloc[0:0].copy()
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=base.crs or target.crs)


def remove_duplicate_roads(gdf: gpd.GeoDataFrame, params: RoadFusionParams | None = None) -> gpd.GeoDataFrame:
    params = params or RoadFusionParams()
    keep = [True] * len(gdf)
    for i, geom_a in enumerate(gdf.geometry):
        if not keep[i]:
            continue
        for j in range(i + 1, len(gdf)):
            geom_b = gdf.geometry.iloc[j]
            if geom_a.buffer(params.dedupe_buffer_m).contains(geom_b) and geom_b.length <= geom_a.length:
                keep[j] = False
            elif geom_b.buffer(params.dedupe_buffer_m).contains(geom_a) and geom_a.length < geom_b.length:
                keep[i] = False
                break
    return gdf.loc[keep].copy()


def snap_road_endpoints(gdf: gpd.GeoDataFrame, reference: gpd.GeoDataFrame, params: RoadFusionParams | None = None) -> gpd.GeoDataFrame:
    params = params or RoadFusionParams()
    if gdf.empty or reference.empty:
        return gdf.copy()
    ref_union = unary_union(list(reference.geometry))
    snapped = gdf.copy()
    new_geoms = []
    for geom in snapped.geometry:
        if not isinstance(geom, LineString):
            new_geoms.append(geom)
            continue
        coords = list(geom.coords)
        start = Point(coords[0])
        end = Point(coords[-1])
        start_proj = ref_union.interpolate(ref_union.project(start))
        end_proj = ref_union.interpolate(ref_union.project(end))
        if start.distance(start_proj) <= params.endpoint_buffer_radius_m:
            coords[0] = (start_proj.x, start_proj.y)
        if end.distance(end_proj) <= params.endpoint_buffer_radius_m:
            coords[-1] = (end_proj.x, end_proj.y)
        new_geoms.append(LineString(coords))
    snapped["geometry"] = new_geoms
    return snapped


def run_road_segment_match_topology(
    base: gpd.GeoDataFrame,
    target: gpd.GeoDataFrame,
    params: RoadFusionParams | None = None,
) -> gpd.GeoDataFrame:
    params = params or RoadFusionParams()
    if base.empty and target.empty:
        template = base if "geometry" in base.columns else target
        return template.iloc[0:0].copy()
    if target.empty:
        passthrough = base.copy()
        passthrough["SRC"] = "base"
        return passthrough
    if base.empty:
        passthrough = target.copy()
        passthrough["SRC"] = "target"
        return passthrough
    base_split = split_features_in_gdf(base, params)
    target_split = split_features_in_gdf(target, params)
    fused = fuse_road_segments(base_split, target_split, params)
    deduped = remove_duplicate_roads(fused, params)
    try:
        deduped["geometry"] = deduped.geometry.apply(lambda geom: linemerge(geom) if isinstance(geom, MultiLineString) else geom)
    except Exception:  # noqa: BLE001
        pass
    return deduped
