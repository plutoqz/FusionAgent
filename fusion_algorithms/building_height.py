from __future__ import annotations

import re
from typing import Mapping

import geopandas as gpd
import pandas as pd

from fusion_algorithms.contracts import BuildingHeightParams


SOURCE_HEIGHT_FIELDS = {
    "OSM": "height_osm",
    "MS": "height_ms",
    "MICROSOFT": "height_ms",
    "GG": "height_google",
    "GOOGLE": "height_google",
    "GOOGLE_OPEN_BUILDINGS": "height_google",
    "OBM": "height_obm",
    "OPENBUILDINGMAP": "height_obm",
}


def source_height_field(source_name: str) -> str:
    key = re.sub(r"[^A-Z0-9]+", "_", source_name.upper()).strip("_")
    if key in SOURCE_HEIGHT_FIELDS:
        return SOURCE_HEIGHT_FIELDS[key]
    return f"height_{key.lower()}" if key else "height_unknown"


def first_height_field(frame: gpd.GeoDataFrame, params: BuildingHeightParams | None = None) -> str | None:
    params = params or BuildingHeightParams()
    candidates = (
        params.canonical_height_field,
        params.height_output_field,
        "height_fused",
        "height_vector_fused",
        "H_Raster",
        "height_raster",
        "Height",
        "HEIGHT",
        "building_h",
        "bld_h",
    )
    for field in candidates:
        if field in frame.columns:
            return field
    return None


def _positive(value: object, *, positive_only: bool = True) -> float | None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(numeric):
        return None
    numeric = float(numeric)
    if positive_only and numeric <= 0:
        return None
    return numeric


def _best_source_heights(
    fused: gpd.GeoDataFrame,
    source: gpd.GeoDataFrame,
    source_height: str,
) -> list[float | None]:
    if source.empty:
        return [None] * len(fused)
    source_frame = source
    if fused.crs is not None:
        if source_frame.crs is None:
            source_frame = source_frame.set_crs(fused.crs)
        elif source_frame.crs != fused.crs:
            source_frame = source_frame.to_crs(fused.crs)
    source_frame = source_frame[source_frame.geometry.notna() & ~source_frame.geometry.is_empty].copy()
    if source_frame.empty:
        return [None] * len(fused)

    sindex = source_frame.sindex
    heights: list[float | None] = []
    for geom in fused.geometry:
        if geom is None or geom.is_empty:
            heights.append(None)
            continue
        best_height = None
        best_area = -1.0
        for candidate_pos in sindex.intersection(geom.bounds):
            candidate = source_frame.iloc[int(candidate_pos)]
            candidate_geom = candidate.geometry
            if candidate_geom is None or candidate_geom.is_empty or not geom.intersects(candidate_geom):
                continue
            area = float(geom.intersection(candidate_geom).area)
            if area > best_area:
                best_area = area
                best_height = candidate.get(source_height)
        heights.append(_positive(best_height, positive_only=False) if best_height is not None else None)
    return heights


def attach_source_heights_and_final(
    fused: gpd.GeoDataFrame,
    source_map: Mapping[str, gpd.GeoDataFrame],
    params: BuildingHeightParams | None = None,
) -> gpd.GeoDataFrame:
    params = params or BuildingHeightParams()
    output = fused.copy()

    raster_source = None
    if "H_Raster" in output.columns:
        raster_source = "H_Raster"
    elif params.height_output_field in output.columns:
        raster_source = params.height_output_field
    if raster_source is not None and params.height_output_field != raster_source:
        output[params.height_output_field] = pd.to_numeric(output[raster_source], errors="coerce")

    source_fields: list[str] = []
    for source_name, source_frame in source_map.items():
        field_name = source_height_field(source_name)
        source_fields.append(field_name)
        if field_name not in output.columns:
            output[field_name] = pd.NA
        source_height = first_height_field(source_frame, params)
        if source_height is None:
            continue
        output[field_name] = _best_source_heights(output, source_frame, source_height)

    reserved_height_fields = {
        "height",
        "height_final",
        "height_final_source",
        "height_vector_fused",
        "height_fused",
        "height_candidates",
        "height_raster",
        "H_Raster",
        params.height_output_field,
    }
    for field in output.columns:
        if field.startswith("height_") and field not in reserved_height_fields and field not in source_fields:
            source_fields.append(field)

    vector_inputs = [field for field in source_fields if field in output.columns]
    if "height_fused" in output.columns:
        vector_inputs.append("height_fused")
    if vector_inputs:
        vector_values = output[vector_inputs].apply(pd.to_numeric, errors="coerce")
        output["height_vector_fused"] = vector_values.max(axis=1, skipna=True)
    elif "height_vector_fused" not in output.columns:
        output["height_vector_fused"] = pd.NA

    final_values: list[float] = []
    final_sources: list[str] = []
    raster_field = params.height_output_field if params.height_output_field in output.columns else raster_source
    for _, row in output.iterrows():
        raster_height = _positive(row.get(raster_field), positive_only=params.positive_only) if raster_field else None
        if raster_height is not None:
            final_values.append(raster_height)
            final_sources.append("raster")
            continue

        best_height = None
        best_source = ""
        for field in vector_inputs:
            value = _positive(row.get(field), positive_only=params.positive_only)
            if value is not None and (best_height is None or value > best_height):
                best_height = value
                best_source = field
        if best_height is not None:
            final_values.append(best_height)
            final_sources.append(best_source)
        else:
            final_values.append(float(params.fallback_height))
            final_sources.append("fallback")

    output["height_final"] = final_values
    output["height_final_source"] = final_sources
    output[params.canonical_height_field] = output["height_final"]
    return output
