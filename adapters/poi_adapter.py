from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import geopandas as gpd
import numpy as np
import pandas as pd

from utils.field_mapping import apply_field_mapping


OUTPUT_COLUMNS = [
    "POI_ID",
    "OSM_ID",
    "REF_ID",
    "MATCH_REF",
    "DIST_M",
    "SRC",
    "NAME",
    "CATEGORY",
    "geometry",
]


@dataclass(frozen=True)
class PoiFusionParameters:
    match_distance_m: float = 250.0


def _to_target_crs(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        gdf = gdf.set_crs(target_crs)
    return gdf.to_crs(target_crs)


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return default


def _resolve_poi_parameters(parameters: Dict[str, object] | None) -> PoiFusionParameters:
    parameters = parameters or {}
    match_distance_m = _as_float(parameters.get("match_distance_m"), 250.0)
    return PoiFusionParameters(match_distance_m=max(0.0, match_distance_m))


def _resolve_feature_ids(gdf: gpd.GeoDataFrame, id_column: str) -> pd.Series:
    if id_column not in gdf.columns:
        return pd.Series(np.arange(1, len(gdf) + 1), index=gdf.index, dtype=int)

    mapped_ids = pd.to_numeric(gdf[id_column], errors="coerce")
    used_ids = {int(value) for value in mapped_ids.dropna().tolist()}
    next_id = max(used_ids, default=0) + 1
    resolved = []
    for value in mapped_ids.tolist():
        if pd.notna(value):
            resolved.append(int(value))
            continue
        while next_id in used_ids:
            next_id += 1
        resolved.append(next_id)
        used_ids.add(next_id)
        next_id += 1
    return pd.Series(resolved, index=gdf.index, dtype=int)


def _prepare_poi(
    gdf: gpd.GeoDataFrame,
    target_crs: str,
    mapping: Dict[str, str] | None,
    id_column: str,
) -> gpd.GeoDataFrame:
    gdf = apply_field_mapping(gdf, mapping or {})
    gdf = _to_target_crs(gdf, target_crs)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf = gdf[gdf.geometry.geom_type.isin(["Point", "MultiPoint"])].copy()

    gdf[id_column] = _resolve_feature_ids(gdf, id_column)
    if "name" not in gdf.columns:
        gdf["name"] = pd.NA
    if "category" not in gdf.columns:
        gdf["category"] = "poi"

    gdf["geometry"] = gdf.geometry.centroid
    return gpd.GeoDataFrame(
        gdf[[id_column, "name", "category", "geometry"]],
        geometry="geometry",
        crs=target_crs,
    )


def _output_row(
    *,
    poi_id: int,
    osm_id: int,
    ref_id: int,
    match_ref: int,
    distance_m: float,
    source: str,
    name: object,
    category: object,
    geometry: object,
) -> Dict[str, object]:
    return {
        "POI_ID": poi_id,
        "OSM_ID": osm_id,
        "REF_ID": ref_id,
        "MATCH_REF": match_ref,
        "DIST_M": distance_m,
        "SRC": source,
        "NAME": name,
        "CATEGORY": category,
        "geometry": geometry,
    }


def _fuse_poi(
    osm_data: gpd.GeoDataFrame,
    ref_data: gpd.GeoDataFrame,
    target_crs: str,
    match_distance_m: float,
) -> gpd.GeoDataFrame:
    rows: List[Dict[str, object]] = []
    matched_ref_positions: set[int] = set()
    ref_sindex = ref_data.sindex if not ref_data.empty else None
    next_poi_id = 1

    for _, osm_row in osm_data.iterrows():
        osm_geom = osm_row.geometry
        matches: List[tuple[int, int, float]] = []

        if ref_sindex is not None:
            for ref_pos in ref_sindex.intersection(osm_geom.buffer(match_distance_m).bounds):
                ref_row = ref_data.iloc[int(ref_pos)]
                distance_m = float(osm_geom.distance(ref_row.geometry))
                if distance_m <= match_distance_m:
                    matches.append((int(ref_pos), int(ref_row["REF_ID"]), distance_m))

        matches.sort(key=lambda item: (item[2], item[1]))
        if matches:
            best_ref_pos, best_ref_id, best_distance = matches[0]
            matched_ref_positions.add(best_ref_pos)
        else:
            best_ref_id = 0
            best_distance = 0.0

        rows.append(
            _output_row(
                poi_id=next_poi_id,
                osm_id=int(osm_row["OSM_ID"]),
                ref_id=best_ref_id,
                match_ref=best_ref_id,
                distance_m=best_distance,
                source="osm",
                name=osm_row["name"],
                category=osm_row["category"],
                geometry=osm_geom,
            )
        )
        next_poi_id += 1

    for ref_pos, (_, ref_row) in enumerate(ref_data.iterrows()):
        if ref_pos in matched_ref_positions:
            continue
        ref_id = int(ref_row["REF_ID"])
        rows.append(
            _output_row(
                poi_id=next_poi_id,
                osm_id=0,
                ref_id=ref_id,
                match_ref=0,
                distance_m=0.0,
                source="ref",
                name=ref_row["name"],
                category=ref_row["category"],
                geometry=ref_row.geometry,
            )
        )
        next_poi_id += 1

    return gpd.GeoDataFrame(rows, columns=OUTPUT_COLUMNS, geometry="geometry", crs=target_crs)


def run_poi_fusion(
    osm_shp: Path,
    ref_shp: Path,
    output_dir: Path,
    target_crs: str = "EPSG:32643",
    field_mapping: Dict[str, Dict[str, str]] | None = None,
    debug: bool = False,
    parameters: Dict[str, object] | None = None,
) -> Path:
    del debug
    resolved_parameters = _resolve_poi_parameters(parameters)

    osm_raw = gpd.read_file(osm_shp)
    ref_raw = gpd.read_file(ref_shp)
    osm_data = _prepare_poi(osm_raw, target_crs, (field_mapping or {}).get("osm"), "OSM_ID")
    ref_data = _prepare_poi(ref_raw, target_crs, (field_mapping or {}).get("ref"), "REF_ID")

    if osm_data.empty and ref_data.empty:
        raise ValueError("Both OSM and reference POI datasets are empty.")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_shp = output_dir / "fused_poi.shp"

    fused = _fuse_poi(
        osm_data=osm_data,
        ref_data=ref_data,
        target_crs=target_crs,
        match_distance_m=resolved_parameters.match_distance_m,
    )
    fused.to_file(output_shp)
    return output_shp
