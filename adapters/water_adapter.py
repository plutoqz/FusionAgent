from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import geopandas as gpd
import numpy as np
import pandas as pd

from utils.field_mapping import apply_field_mapping


OUTPUT_COLUMNS = [
    "OSM_ID",
    "REF_ID",
    "MATCH_REF",
    "OV_RATIO",
    "MATCH_CNT",
    "SRC",
    "NAME",
    "FCLASS",
    "WATER_TY",
    "geometry",
]


@dataclass(frozen=True)
class WaterFusionParameters:
    overlap_threshold: float = 0.1


def _to_target_crs(gdf: gpd.GeoDataFrame, target_crs: str) -> gpd.GeoDataFrame:
    if gdf.crs is None:
        gdf = gdf.set_crs(target_crs)
    return gdf.to_crs(target_crs)


def _as_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return default


def _resolve_water_parameters(parameters: Dict[str, object] | None) -> WaterFusionParameters:
    parameters = parameters or {}
    overlap_threshold = _as_float(parameters.get("overlap_threshold"), 0.1)
    return WaterFusionParameters(overlap_threshold=min(1.0, max(0.0, overlap_threshold)))


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


def _prepare_water(
    gdf: gpd.GeoDataFrame,
    target_crs: str,
    mapping: Dict[str, str] | None,
    id_column: str,
) -> gpd.GeoDataFrame:
    gdf = apply_field_mapping(gdf, mapping or {})
    gdf = _to_target_crs(gdf, target_crs)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    gdf = gdf[gdf.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    gdf = gdf[gdf.geometry.area > 0].copy()

    gdf[id_column] = _resolve_feature_ids(gdf, id_column)
    for column, default in {"name": pd.NA, "fclass": "water", "water_ty": pd.NA}.items():
        if column not in gdf.columns:
            gdf[column] = default

    return gpd.GeoDataFrame(
        gdf[[id_column, "name", "fclass", "water_ty", "geometry"]],
        geometry="geometry",
        crs=target_crs,
    )


def _output_row(
    *,
    osm_id: int,
    ref_id: int,
    match_ref: int,
    overlap_ratio: float,
    match_count: int,
    source: str,
    name: object,
    fclass: object,
    water_type: object,
    geometry: object,
) -> Dict[str, object]:
    return {
        "OSM_ID": osm_id,
        "REF_ID": ref_id,
        "MATCH_REF": match_ref,
        "OV_RATIO": overlap_ratio,
        "MATCH_CNT": match_count,
        "SRC": source,
        "NAME": name,
        "FCLASS": fclass,
        "WATER_TY": water_type,
        "geometry": geometry,
    }


def _fuse_water(
    osm_data: gpd.GeoDataFrame,
    ref_data: gpd.GeoDataFrame,
    target_crs: str,
    overlap_threshold: float,
) -> gpd.GeoDataFrame:
    rows: List[Dict[str, object]] = []
    matched_ref_positions: set[int] = set()
    ref_sindex = ref_data.sindex if not ref_data.empty else None

    for _, osm_row in osm_data.iterrows():
        osm_geom = osm_row.geometry
        osm_area = float(osm_geom.area)
        matches: List[tuple[int, float]] = []

        if ref_sindex is not None and osm_area > 0:
            for ref_pos in ref_sindex.intersection(osm_geom.bounds):
                ref_row = ref_data.iloc[int(ref_pos)]
                if not osm_geom.intersects(ref_row.geometry):
                    continue
                overlap_ratio = float(osm_geom.intersection(ref_row.geometry).area / osm_area)
                if overlap_ratio >= overlap_threshold:
                    matches.append((int(ref_row["REF_ID"]), overlap_ratio))
                    matched_ref_positions.add(int(ref_pos))

        matches.sort(key=lambda item: (-item[1], item[0]))
        best_ref_id = matches[0][0] if matches else 0
        best_overlap = matches[0][1] if matches else 0.0

        rows.append(
            _output_row(
                osm_id=int(osm_row["OSM_ID"]),
                ref_id=best_ref_id,
                match_ref=best_ref_id,
                overlap_ratio=best_overlap,
                match_count=len(matches),
                source="osm",
                name=osm_row["name"],
                fclass=osm_row["fclass"],
                water_type=osm_row["water_ty"],
                geometry=osm_geom,
            )
        )

    for ref_pos, (_, ref_row) in enumerate(ref_data.iterrows()):
        if ref_pos in matched_ref_positions:
            continue
        ref_id = int(ref_row["REF_ID"])
        rows.append(
            _output_row(
                osm_id=0,
                ref_id=ref_id,
                match_ref=0,
                overlap_ratio=0.0,
                match_count=0,
                source="ref",
                name=ref_row["name"],
                fclass=ref_row["fclass"],
                water_type=ref_row["water_ty"],
                geometry=ref_row.geometry,
            )
        )

    return gpd.GeoDataFrame(rows, columns=OUTPUT_COLUMNS, geometry="geometry", crs=target_crs)


def run_water_fusion(
    osm_shp: Path,
    ref_shp: Path,
    output_dir: Path,
    target_crs: str = "EPSG:32643",
    field_mapping: Dict[str, Dict[str, str]] | None = None,
    debug: bool = False,
    parameters: Dict[str, object] | None = None,
) -> Path:
    del debug
    resolved_parameters = _resolve_water_parameters(parameters)

    osm_raw = gpd.read_file(osm_shp)
    ref_raw = gpd.read_file(ref_shp)
    osm_data = _prepare_water(osm_raw, target_crs, (field_mapping or {}).get("osm"), "OSM_ID")
    ref_data = _prepare_water(ref_raw, target_crs, (field_mapping or {}).get("ref"), "REF_ID")

    if osm_data.empty and ref_data.empty:
        raise ValueError("Both OSM and reference water datasets are empty.")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_shp = output_dir / "fused_water.shp"

    fused = _fuse_water(
        osm_data=osm_data,
        ref_data=ref_data,
        target_crs=target_crs,
        overlap_threshold=resolved_parameters.overlap_threshold,
    )
    fused.to_file(output_shp)
    return output_shp
