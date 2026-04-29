from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

import geopandas as gpd
import pandas as pd

from fusion_algorithms.contracts import PoiFusionParams


def _name_score(left: object, right: object) -> float:
    left_text = "" if pd.isna(left) else str(left).strip().lower()
    right_text = "" if pd.isna(right) else str(right).strip().lower()
    if not left_text or not right_text:
        return 0.0
    if left_text == right_text:
        return 1.0
    return SequenceMatcher(None, left_text, right_text).ratio()


def _geohash_neighbors(value: str, rings: int) -> set[str]:
    values = {value}
    if rings <= 0:
        return values
    try:
        import geohash  # type: ignore
    except Exception:  # noqa: BLE001
        return values
    frontier = {value}
    for _ in range(rings):
        next_frontier = set()
        for item in frontier:
            try:
                next_frontier.update(geohash.neighbors(item))
            except Exception:  # noqa: BLE001
                continue
        values.update(next_frontier)
        frontier = next_frontier
    return values


def build_geohash_candidates(
    base: gpd.GeoDataFrame,
    target: gpd.GeoDataFrame,
    params: PoiFusionParams | None = None,
    geohash_column: str = "GeoHash",
) -> pd.DataFrame:
    params = params or PoiFusionParams()
    rows: list[dict[str, Any]] = []
    if geohash_column not in base.columns or geohash_column not in target.columns:
        return pd.DataFrame(columns=["base_index", "target_index", "name_score"])
    target_by_hash: dict[str, list[int]] = {}
    for pos, value in enumerate(target[geohash_column].astype(str).tolist()):
        target_by_hash.setdefault(value, []).append(pos)
    for base_pos, base_row in base.iterrows():
        base_hash = str(base_row[geohash_column])
        for candidate_hash in _geohash_neighbors(base_hash, params.neighbor_rings):
            for target_pos in target_by_hash.get(candidate_hash, []):
                target_row = target.iloc[target_pos]
                score = _name_score(base_row.get("name"), target_row.get("name"))
                if score >= params.name_similarity_threshold or score == 0.0:
                    rows.append({"base_index": int(base_pos), "target_index": target_pos, "name_score": score})
    return pd.DataFrame(rows)


def match_poi_neighbors(
    base: gpd.GeoDataFrame,
    target: gpd.GeoDataFrame,
    params: PoiFusionParams | None = None,
) -> pd.DataFrame:
    params = params or PoiFusionParams()
    candidates = build_geohash_candidates(base, target, params)
    if not candidates.empty:
        return candidates.sort_values("name_score", ascending=False).drop_duplicates("base_index")
    if base.empty or target.empty:
        return candidates
    rows = []
    target_sindex = target.sindex
    for base_pos, (_, base_row) in enumerate(base.iterrows()):
        for target_pos in target_sindex.intersection(base_row.geometry.buffer(params.duplicate_distance_m).bounds):
            target_row = target.iloc[int(target_pos)]
            dist = float(base_row.geometry.distance(target_row.geometry))
            if dist <= params.duplicate_distance_m:
                rows.append(
                    {
                        "base_index": base_pos,
                        "target_index": int(target_pos),
                        "distance_m": dist,
                        "name_score": _name_score(base_row.get("name"), target_row.get("name")),
                    }
                )
    if not rows:
        return pd.DataFrame(columns=["base_index", "target_index", "distance_m", "name_score"])
    return pd.DataFrame(rows).sort_values(["distance_m", "name_score"], ascending=[True, False]).drop_duplicates("base_index")


def merge_poi_by_name_source_priority(
    base: gpd.GeoDataFrame,
    target: gpd.GeoDataFrame,
    matches: pd.DataFrame,
    params: PoiFusionParams | None = None,
) -> gpd.GeoDataFrame:
    params = params or PoiFusionParams()
    matched_base = set(matches["base_index"].tolist()) if not matches.empty else set()
    matched_target = set(matches["target_index"].tolist()) if not matches.empty else set()
    rows = []
    for base_pos, (_, row) in enumerate(base.iterrows()):
        data = row.to_dict()
        data["SRC"] = "base"
        data["MATCHED"] = base_pos in matched_base
        rows.append(data)
    for target_pos, (_, row) in enumerate(target.iterrows()):
        if target_pos in matched_target:
            continue
        data = row.to_dict()
        data["SRC"] = "target"
        data["MATCHED"] = False
        rows.append(data)
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=base.crs or target.crs)


def run_poi_geohash_priority_fusion(
    sources: dict[str, gpd.GeoDataFrame],
    params: PoiFusionParams | None = None,
) -> gpd.GeoDataFrame:
    params = params or PoiFusionParams()
    ordered = [name for name in params.source_priority_order if name in sources]
    if not ordered:
        raise ValueError("No POI sources available.")
    current = sources[ordered[0]].copy()
    for name in ordered[1:]:
        matches = match_poi_neighbors(current, sources[name], params)
        current = merge_poi_by_name_source_priority(current, sources[name], matches, params)
    return current
