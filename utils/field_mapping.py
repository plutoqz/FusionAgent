from __future__ import annotations

from typing import Dict, Iterable, List

import geopandas as gpd
import pandas as pd


class FieldMappingError(ValueError):
    pass


def apply_field_mapping(gdf: gpd.GeoDataFrame, mapping: Dict[str, str]) -> gpd.GeoDataFrame:
    """Rename columns from user mapping: canonical -> actual."""
    if not mapping:
        return gdf

    gdf = gdf.copy()
    rename_map: Dict[str, str] = {}
    for canonical, actual in mapping.items():
        if not actual:
            continue
        if actual not in gdf.columns:
            raise FieldMappingError(f"Mapped source field not found: '{actual}' for canonical '{canonical}'")
        if canonical != actual:
            rename_map[actual] = canonical
    if rename_map:
        gdf = gdf.rename(columns=rename_map)
    return gdf


def ensure_columns(
    gdf: gpd.GeoDataFrame,
    required: Iterable[str],
    optional_defaults: Dict[str, object] | None = None,
    context: str = "",
) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    optional_defaults = optional_defaults or {}

    missing_required = [col for col in required if col not in gdf.columns]
    if missing_required:
        prefix = f"{context}: " if context else ""
        raise FieldMappingError(f"{prefix}missing required fields: {', '.join(missing_required)}")

    for col, default in optional_defaults.items():
        if col not in gdf.columns:
            gdf[col] = default
    return gdf


def ensure_numeric(gdf: gpd.GeoDataFrame, columns: Iterable[str]) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    for col in columns:
        if col in gdf.columns:
            gdf[col] = pd.to_numeric(gdf[col], errors="coerce")
    return gdf
