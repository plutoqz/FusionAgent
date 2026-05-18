from __future__ import annotations

from typing import Callable

import geopandas as gpd
import pandas as pd

from kg.track_b_source_contract import get_track_b_source_contract


_GEOHASH_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def normalize_track_b_source_frame(
    source_id: str,
    frame: gpd.GeoDataFrame,
    *,
    target_crs: str,
    geohash_precision: int = 8,
) -> gpd.GeoDataFrame:
    contract = get_track_b_source_contract(source_id)
    if contract is None:
        raise KeyError(f"Unknown Track B source_id={source_id}")

    normalized = frame.copy()
    if normalized.crs is None:
        normalized = normalized.set_crs("EPSG:4326")
    normalized = normalized.to_crs(target_crs)
    normalized = normalized[normalized.geometry.notna() & ~normalized.geometry.is_empty].copy()
    normalized = normalized.reset_index(drop=True)
    normalized["source_id"] = source_id
    normalized["track_b_theme"] = contract.theme
    normalized["field_mapping_profile"] = contract.field_mapping_profile

    handler = _PROFILE_HANDLERS.get(contract.field_mapping_profile)
    if handler is None:
        raise KeyError(f"Unsupported Track B field mapping profile={contract.field_mapping_profile}")
    normalized = handler(normalized, geohash_precision=geohash_precision)
    return normalized.reset_index(drop=True)


def _normalize_building_osm(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["osm_id", "id", "objectid", "fid"]))
    frame["name"] = _coalesce(frame, ["name", "bld_name", "building_n"])
    frame["building_class"] = _coalesce(frame, ["building", "type", "class", "use"], default="building")
    frame["confidence"] = _coalesce(frame, ["confidence"], default=1.0)
    return _filter_geometry(frame, {"Polygon", "MultiPolygon"})


def _normalize_building_reference(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(
        _coalesce(frame, ["id", "sourceid", "OBJECTID", "objectid", "fid"])
    )
    frame["name"] = _coalesce(frame, ["name", "Name"])
    frame["building_class"] = _coalesce(frame, ["type", "class", "CATEGORY"], default="building")
    frame["confidence"] = _coalesce(frame, ["confidence", "probability", "prob"], default=1.0)
    return _filter_geometry(frame, {"Polygon", "MultiPolygon"})


def _normalize_road_osm(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["osm_id", "id", "objectid", "fid"]))
    frame["name"] = _coalesce(frame, ["name", "ref"])
    frame["fclass"] = _stringify(_coalesce(frame, ["fclass", "highway", "class"], default="road"))
    frame["road_class"] = _stringify(_coalesce(frame, ["road_class", "fclass", "highway", "class"], default="road"))
    return _filter_geometry(frame, {"LineString", "MultiLineString"})


def _normalize_road_overture(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["id", "segment_id", "road_id", "fid"]))
    frame["FID_1"] = _resolved_numeric_ids(frame["source_feature_id"])
    frame["name"] = _coalesce(frame, ["name", "names.primary", "names_primary", "primary_name", "ref"])
    frame["fclass"] = _stringify(_coalesce(frame, ["class", "subtype", "type"], default="road"))
    frame["road_class"] = _stringify(_coalesce(frame, ["road_class", "class", "subtype", "type"], default="road"))
    return _filter_geometry(frame, {"LineString", "MultiLineString"})


def _normalize_water_osm_polygon(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["osm_id", "id", "objectid", "fid"]))
    frame["name"] = _coalesce(frame, ["name", "waterway", "natural"])
    frame["fclass"] = _stringify(_coalesce(frame, ["fclass", "natural"], default="water"))
    frame["water_ty"] = _stringify(_coalesce(frame, ["water_ty", "water", "natural", "fclass"], default="polygon"))
    return _filter_geometry(frame, {"Polygon", "MultiPolygon"})


def _normalize_water_local_reference(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["Hylak_id", "lake_id", "id", "OBJECTID", "fid"]))
    frame["name"] = _coalesce(frame, ["Lake_name", "name", "Name"])
    frame["fclass"] = _stringify(_coalesce(frame, ["fclass", "Lake_type", "type"], default="lake"))
    frame["water_ty"] = _stringify(_coalesce(frame, ["Lake_type", "water_ty", "type"], default="polygon"))
    return _filter_geometry(frame, {"Polygon", "MultiPolygon"})


def _normalize_water_hydrorivers(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["HYRIV_ID", "river_id", "id"]))
    frame["name"] = _coalesce(frame, ["name", "River_name", "river_name"])
    frame["fclass"] = _stringify(_coalesce(frame, ["fclass"], default="river"))
    frame["water_ty"] = _stringify(_coalesce(frame, ["water_ty"], default="line"))
    return _filter_geometry(frame, {"LineString", "MultiLineString"})


def _normalize_water_hydrolakes(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["Hylak_id", "lake_id", "id"]))
    frame["name"] = _coalesce(frame, ["Lake_name", "name", "Name"])
    frame["fclass"] = _stringify(_coalesce(frame, ["fclass"], default="lake"))
    frame["water_ty"] = _stringify(_coalesce(frame, ["Lake_type", "water_ty", "type"], default="polygon"))
    return _filter_geometry(frame, {"Polygon", "MultiPolygon"})


def _normalize_water_overture(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["id", "fid"]))
    frame["name"] = _coalesce(frame, ["name", "names.primary", "names_primary"])
    frame["fclass"] = _stringify(_coalesce(frame, ["class", "subtype"], default="water"))
    frame["water_ty"] = _stringify(_coalesce(frame, ["type", "subtype"], default="water"))
    return _filter_geometry(frame, {"LineString", "MultiLineString", "Polygon", "MultiPolygon"})


def _normalize_poi_osm(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["osm_id", "id", "objectid", "fid"]))
    frame["name"] = _coalesce(frame, ["name", "alt_name"])
    frame["name_alt"] = _coalesce(frame, ["alt_name", "name_en"])
    frame["category"] = _stringify(_coalesce(frame, ["fclass", "amenity", "type", "class"], default="poi"))
    frame = _ensure_point_geometry(frame)
    frame["GeoHash"] = _ensure_geohash(frame, precision=geohash_precision)
    return frame


def _normalize_poi_gns(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["ufi", "uni", "id"]))
    frame["name"] = _coalesce(frame, ["full_name", "full_nm_nd", "name", "display"])
    frame["name_alt"] = _coalesce(frame, ["full_nm_nd", "generic"])
    frame["category"] = _stringify(_coalesce(frame, ["desig_cd", "fc", "type"], default="poi"))
    frame = _ensure_point_geometry(frame)
    frame["GeoHash"] = _ensure_geohash(frame, precision=geohash_precision)
    return frame


def _normalize_poi_rh(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["id", "sourceid"]))
    frame["name"] = _coalesce(frame, ["name", "alternaten"])
    frame["name_alt"] = _coalesce(frame, ["alternaten"])
    frame["category"] = _stringify(_coalesce(frame, ["type", "class", "label"], default="poi"))
    frame = _ensure_point_geometry(frame)
    frame["GeoHash"] = _ensure_geohash(frame, precision=geohash_precision)
    return frame


def _normalize_poi_overture(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["id", "sourceid"]))
    frame["name"] = _coalesce(frame, ["name", "names.primary", "names_primary"])
    frame["name_alt"] = _coalesce(frame, ["brand"])
    frame["category"] = _stringify(_coalesce(frame, ["category", "class", "type"], default="poi"))
    frame = _ensure_point_geometry(frame)
    frame["GeoHash"] = _ensure_geohash(frame, precision=geohash_precision)
    return frame


_PROFILE_HANDLERS: dict[str, Callable[[gpd.GeoDataFrame], gpd.GeoDataFrame]] = {
    "fields.building.osm": _normalize_building_osm,
    "fields.building.microsoft": _normalize_building_reference,
    "fields.building.google": _normalize_building_reference,
    "fields.building.openbuildingmap": _normalize_building_reference,
    "fields.building.google_open_buildings_vector": _normalize_building_reference,
    "fields.road.osm": _normalize_road_osm,
    "fields.road.overture_transportation": _normalize_road_overture,
    "fields.water.osm_polygon": _normalize_water_osm_polygon,
    "fields.water.local_reference": _normalize_water_local_reference,
    "fields.water.hydrorivers_line": _normalize_water_hydrorivers,
    "fields.water.hydrolakes_polygon": _normalize_water_hydrolakes,
    "fields.water.overture": _normalize_water_overture,
    "fields.poi.osm": _normalize_poi_osm,
    "fields.poi.gns": _normalize_poi_gns,
    "fields.poi.rh": _normalize_poi_rh,
    "fields.poi.overture_places": _normalize_poi_overture,
}


def _filter_geometry(frame: gpd.GeoDataFrame, allowed: set[str]) -> gpd.GeoDataFrame:
    if frame.empty:
        return frame
    filtered = frame[frame.geometry.geom_type.isin(sorted(allowed))].copy()
    return filtered.reset_index(drop=True)


def _ensure_point_geometry(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if frame.empty:
        return frame
    filtered = frame[frame.geometry.geom_type.isin(["Point", "MultiPoint"])].copy()
    if filtered.empty:
        return filtered
    filtered["geometry"] = filtered.geometry.representative_point()
    return filtered.reset_index(drop=True)


def _coalesce(frame: gpd.GeoDataFrame, columns: list[str], default: object = pd.NA) -> pd.Series:
    values = [pd.NA for _ in range(len(frame))]
    for column in columns:
        if column not in frame.columns:
            continue
        series = frame[column].tolist()
        for index, value in enumerate(series):
            if _is_missing(values[index]) and not _is_missing(value):
                values[index] = value
    if not _is_missing(default):
        values = [default if _is_missing(value) else value for value in values]
    return pd.Series(values, index=frame.index, dtype="object")


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except Exception:  # noqa: BLE001
        pass
    return isinstance(value, str) and not value.strip()


def _stringify(series: pd.Series) -> pd.Series:
    return series.apply(lambda value: "" if _is_missing(value) else str(value))


def _resolved_numeric_ids(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    used_ids = {int(value) for value in numeric.dropna().tolist()}
    next_id = max(used_ids, default=0) + 1
    resolved: list[int] = []
    for value in numeric.tolist():
        if pd.notna(value):
            resolved.append(int(value))
            continue
        while next_id in used_ids:
            next_id += 1
        resolved.append(next_id)
        used_ids.add(next_id)
        next_id += 1
    return pd.Series(resolved, index=series.index, dtype=int)


def _ensure_geohash(frame: gpd.GeoDataFrame, *, precision: int) -> pd.Series:
    existing = _coalesce(frame, ["GeoHash", "geohash"])
    if not existing.apply(_is_missing).any():
        return _stringify(existing)

    geographic = frame.to_crs("EPSG:4326")
    computed: list[str] = []
    for current, geometry in zip(existing.tolist(), geographic.geometry.tolist()):
        if not _is_missing(current):
            computed.append(str(current))
            continue
        point = geometry.representative_point() if geometry is not None else None
        if point is None or point.is_empty:
            computed.append("")
            continue
        computed.append(_encode_geohash(point.x, point.y, precision=precision))
    return pd.Series(computed, index=frame.index, dtype="object")


def _encode_geohash(lon: float, lat: float, *, precision: int = 8) -> str:
    lat_interval = [-90.0, 90.0]
    lon_interval = [-180.0, 180.0]
    geohash: list[str] = []
    bits = [16, 8, 4, 2, 1]
    bit = 0
    ch = 0
    even = True
    while len(geohash) < precision:
        if even:
            midpoint = sum(lon_interval) / 2.0
            if lon >= midpoint:
                ch |= bits[bit]
                lon_interval[0] = midpoint
            else:
                lon_interval[1] = midpoint
        else:
            midpoint = sum(lat_interval) / 2.0
            if lat >= midpoint:
                ch |= bits[bit]
                lat_interval[0] = midpoint
            else:
                lat_interval[1] = midpoint
        even = not even
        if bit < 4:
            bit += 1
        else:
            geohash.append(_GEOHASH_BASE32[ch])
            bit = 0
            ch = 0
    return "".join(geohash)
