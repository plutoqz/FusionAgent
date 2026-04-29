from __future__ import annotations

from typing import Any

import geopandas as gpd

from fusion_algorithms.contracts import ConflictDetectionParams


def detect_spatial_conflicts(
    gdf: gpd.GeoDataFrame,
    params: ConflictDetectionParams | None = None,
) -> list[dict[str, Any]]:
    params = params or ConflictDetectionParams()
    frame = gdf.copy()
    if params.buffer_distance_m:
        frame["geometry"] = frame.geometry.buffer(params.buffer_distance_m)
    conflicts: list[dict[str, Any]] = []
    geoms = list(frame.geometry)
    for i, geom_a in enumerate(geoms):
        if geom_a is None or geom_a.is_empty:
            continue
        for j in range(i + 1, len(geoms)):
            geom_b = geoms[j]
            if geom_b is None or geom_b.is_empty:
                continue
            if not geom_a.intersects(geom_b):
                continue
            inter = geom_a.intersection(geom_b)
            if params.touch_policy == "ignore_touches" and inter.area <= 0:
                continue
            if inter.area < params.overlap_area_min:
                continue
            conflicts.append(
                {
                    "left_id": int(frame.index[i]) if hasattr(frame.index[i], "__int__") else str(frame.index[i]),
                    "right_id": int(frame.index[j]) if hasattr(frame.index[j], "__int__") else str(frame.index[j]),
                    "overlap_area": float(inter.area),
                }
            )
    return conflicts
