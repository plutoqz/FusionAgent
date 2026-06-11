from __future__ import annotations

import json
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
    source_semantics=None,
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

    if source_semantics is not None:
        normalized["field_mapping_profile"] = source_semantics.field_mapping_profile
        normalized = _normalize_from_semantics(
            normalized,
            source_semantics,
            contract.theme,
            geohash_precision,
        )
    else:
        handler = _PROFILE_HANDLERS.get(contract.field_mapping_profile)
        if handler is None:
            raise KeyError(f"Unsupported Track B field mapping profile={contract.field_mapping_profile}")
        normalized = handler(normalized, geohash_precision=geohash_precision)
    return normalized.reset_index(drop=True)


def _semantic_candidates(source_semantics, canonical_field: str) -> list[str]:
    matched = source_semantics.matched_fields.get(canonical_field)
    if matched is None:
        return []
    ordered: list[str] = []
    if matched.matched_field:
        ordered.append(matched.matched_field)
    ordered.extend(item for item in matched.candidate_fields if item not in ordered)
    return ordered


def _normalize_from_semantics(
    frame: gpd.GeoDataFrame,
    source_semantics,
    theme: str,
    geohash_precision: int,
) -> gpd.GeoDataFrame:
    if theme == "building":
        frame["source_feature_id"] = _stringify(
            _coalesce(frame, _semantic_candidates(source_semantics, "source_feature_id"))
        )
        frame["name"] = _coalesce(frame, _semantic_candidates(source_semantics, "name"))
        frame["height_m"] = _numeric_coalesce(frame, _semantic_candidates(source_semantics, "height_m"))
        frame["building_class"] = _coalesce(
            frame,
            _semantic_candidates(source_semantics, "building_class"),
            default="building",
        )
        frame["confidence"] = _coalesce(frame, _semantic_candidates(source_semantics, "confidence"), default=1.0)
        return _filter_geometry(frame, {"Polygon", "MultiPolygon"})
    if theme == "road":
        frame["source_feature_id"] = _stringify(
            _coalesce(frame, _semantic_candidates(source_semantics, "source_feature_id"))
        )
        frame["name"] = _coalesce(frame, _semantic_candidates(source_semantics, "name"))
        frame["road_class"] = _stringify(
            _coalesce(frame, _semantic_candidates(source_semantics, "road_class"), default="road")
        )
        frame["fclass"] = frame["road_class"]
        frame["surface"] = _coalesce(frame, _semantic_candidates(source_semantics, "surface"))
        frame["lanes"] = _coalesce(frame, _semantic_candidates(source_semantics, "lanes"))
        return _filter_geometry(frame, {"LineString", "MultiLineString"})
    if theme == "water":
        frame["source_feature_id"] = _stringify(
            _coalesce(frame, _semantic_candidates(source_semantics, "source_feature_id"))
        )
        frame["name"] = _coalesce(frame, _semantic_candidates(source_semantics, "name"))
        feature_kind_candidates = _semantic_candidates(source_semantics, "feature_kind")
        literal_kind = next((item for item in feature_kind_candidates if item in {"line", "polygon"}), None)
        frame["feature_kind"] = literal_kind or _coalesce(frame, feature_kind_candidates, default="water")
        frame["water_class"] = _stringify(
            _coalesce(frame, _semantic_candidates(source_semantics, "water_class"), default="water")
        )
        frame["fclass"] = frame["water_class"]
        frame["water_ty"] = frame["feature_kind"]
        frame["perennial_flag"] = _coalesce(frame, _semantic_candidates(source_semantics, "perennial_flag"))
        return _filter_geometry(frame, {"LineString", "MultiLineString", "Polygon", "MultiPolygon"})
    if theme == "waterways":
        frame["source_feature_id"] = _stringify(
            _coalesce(frame, _semantic_candidates(source_semantics, "source_feature_id"))
        )
        frame["name"] = _coalesce(frame, _semantic_candidates(source_semantics, "name"))
        frame["name_en"] = _coalesce(frame, _semantic_candidates(source_semantics, "name_en"))
        frame["name_ur"] = _coalesce(frame, _semantic_candidates(source_semantics, "name_ur"))
        frame["feature_kind"] = "line"
        frame["water_class"] = _stringify(
            _coalesce(frame, _semantic_candidates(source_semantics, "water_class"), default="waterway")
        )
        frame["fclass"] = frame["water_class"]
        frame["water_ty"] = "line"
        return _filter_geometry(frame, {"LineString", "MultiLineString"})
    if theme == "poi":
        frame["source_feature_id"] = _stringify(
            _coalesce(frame, _semantic_candidates(source_semantics, "source_feature_id"))
        )
        frame["name"] = _coalesce(frame, _semantic_candidates(source_semantics, "name"))
        frame["name_alt"] = _coalesce(frame, _semantic_candidates(source_semantics, "name_alt"))
        frame["category"] = _stringify(
            _coalesce(frame, _semantic_candidates(source_semantics, "category"), default="poi")
        )
        frame["admin_country"] = _coalesce(frame, _semantic_candidates(source_semantics, "admin_country"))
        frame = _ensure_point_geometry(frame)
        frame["GeoHash"] = _ensure_geohash(frame, precision=geohash_precision)
        return frame
    return frame


def _normalize_building_osm(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(
        _coalesce(frame, ["osm_id", "osm_way_id", "osm_rel_id", "id", "objectid", "fid"])
    )
    frame["name"] = _coalesce(frame, ["name", "bld_name", "building_n"])
    frame["height_m"] = _numeric_coalesce(frame, ["height", "Height", "HEIGHT", "building_h", "bld_h"])
    frame["building_class"] = _coalesce(frame, ["building", "type", "class", "use"], default="building")
    frame["confidence"] = _coalesce(frame, ["confidence"], default=1.0)
    return _filter_geometry(frame, {"Polygon", "MultiPolygon"})


def _normalize_building_reference(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    source_feature_id = _coalesce(frame, ["id", "quadkey", "sourceid", "OBJECTID", "objectid", "fid"])
    if source_feature_id.apply(_is_missing).any() and {"latitude", "longitude"}.issubset(frame.columns):
        lat_lon_id = frame["latitude"].astype(str) + "," + frame["longitude"].astype(str)
        source_feature_id = source_feature_id.where(~source_feature_id.apply(_is_missing), lat_lon_id)
    frame["source_feature_id"] = _stringify(source_feature_id)
    frame["name"] = _coalesce(frame, ["name", "Name"])
    frame["height_m"] = _numeric_coalesce(frame, ["height", "Height", "HEIGHT", "building_h", "bld_h"])
    frame["building_class"] = _coalesce(frame, ["type", "class", "CATEGORY"], default="building")
    frame["confidence"] = _coalesce(frame, ["confidence", "probability", "prob"], default=1.0)
    return _filter_geometry(frame, {"Polygon", "MultiPolygon"})


def _normalize_road_osm(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["osm_id", "id", "objectid", "fid"]))
    frame["name"] = _coalesce(frame, ["name", "ref"])
    frame["fclass"] = _stringify(_coalesce(frame, ["fclass", "highway", "class"], default="road"))
    frame["road_class"] = _stringify(_coalesce(frame, ["road_class", "fclass", "highway", "class"], default="road"))
    frame["surface"] = _coalesce(frame, ["surface"])
    frame["lanes"] = _coalesce(frame, ["lanes"])
    return _filter_geometry(frame, {"LineString", "MultiLineString"})


def _normalize_road_overture(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["id", "segment_id", "road_id", "fid"]))
    frame["FID_1"] = _resolved_numeric_ids(frame["source_feature_id"])
    frame["name"] = _coalesce(frame, ["name", "names.primary", "names_primary", "primary_name", "ref"])
    frame["fclass"] = _stringify(_coalesce(frame, ["class", "subclass", "subtype", "type"], default="road"))
    frame["road_class"] = _stringify(
        _coalesce(frame, ["road_class", "class", "subclass", "subtype", "type"], default="road")
    )
    frame["surface"] = _coalesce(frame, ["surface"])
    frame["lanes"] = _coalesce(frame, ["lane_count", "lanes"])
    return _filter_geometry(frame, {"LineString", "MultiLineString"})


def _normalize_water_osm_polygon(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["osm_id", "id", "objectid", "fid"]))
    frame["name"] = _coalesce(frame, ["name", "waterway", "natural"])
    frame["fclass"] = _stringify(_coalesce(frame, ["fclass", "natural"], default="water"))
    frame["water_ty"] = _stringify(_coalesce(frame, ["water_ty", "water", "natural", "fclass"], default="polygon"))
    frame["feature_kind"] = pd.Series(["polygon"] * len(frame), index=frame.index, dtype="object")
    frame["water_class"] = _stringify(_coalesce(frame, ["fclass", "waterway", "natural"], default="water"))
    frame["perennial_flag"] = _coalesce(frame, ["perennial_flag", "perennial"])
    return _filter_geometry(frame, {"Polygon", "MultiPolygon"})


def _normalize_water_osm_line(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["osm_id", "id", "objectid", "fid"]))
    frame["name"] = _coalesce(frame, ["name", "waterway", "fclass"])
    frame["fclass"] = _stringify(_coalesce(frame, ["fclass", "waterway"], default="river"))
    frame["water_ty"] = _stringify(_coalesce(frame, ["water_ty", "waterway"], default="line"))
    frame["feature_kind"] = pd.Series(["line"] * len(frame), index=frame.index, dtype="object")
    frame["water_class"] = _stringify(_coalesce(frame, ["waterway", "fclass"], default="river"))
    frame["perennial_flag"] = _coalesce(frame, ["perennial_flag", "intermittent"])
    return _filter_geometry(frame, {"LineString", "MultiLineString"})


def _normalize_water_local_reference(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["Hylak_id", "lake_id", "id", "OBJECTID", "fid"]))
    frame["name"] = _coalesce(frame, ["Lake_name", "name", "Name"])
    frame["fclass"] = _stringify(_coalesce(frame, ["fclass", "Lake_type", "type"], default="lake"))
    frame["water_ty"] = _stringify(_coalesce(frame, ["Lake_type", "water_ty", "type"], default="polygon"))
    frame["feature_kind"] = pd.Series(["polygon"] * len(frame), index=frame.index, dtype="object")
    frame["water_class"] = _stringify(_coalesce(frame, ["type", "class", "Lake_type"], default="lake"))
    frame["perennial_flag"] = _coalesce(frame, ["perennial_flag", "Depth_avg"])
    return _filter_geometry(frame, {"Polygon", "MultiPolygon"})


def _normalize_water_hydrorivers(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["HYRIV_ID", "river_id", "id"]))
    frame["name"] = _coalesce(frame, ["name", "River_name", "river_name"])
    frame["fclass"] = _stringify(_coalesce(frame, ["fclass"], default="river"))
    frame["water_ty"] = _stringify(_coalesce(frame, ["water_ty"], default="line"))
    frame["feature_kind"] = pd.Series(["line"] * len(frame), index=frame.index, dtype="object")
    frame["water_class"] = _stringify(_coalesce(frame, ["ORD_STRA", "fclass"], default="river"))
    frame["perennial_flag"] = _coalesce(frame, ["DIS_AV_CMS", "perennial_flag"])
    return _filter_geometry(frame, {"LineString", "MultiLineString"})


def _normalize_water_hydrolakes(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["Hylak_id", "lake_id", "id"]))
    frame["name"] = _coalesce(frame, ["Lake_name", "name", "Name"])
    frame["fclass"] = _stringify(_coalesce(frame, ["fclass"], default="lake"))
    frame["water_ty"] = _stringify(_coalesce(frame, ["Lake_type", "water_ty", "type"], default="polygon"))
    frame["feature_kind"] = pd.Series(["polygon"] * len(frame), index=frame.index, dtype="object")
    frame["water_class"] = _stringify(_coalesce(frame, ["Lake_type", "fclass"], default="lake"))
    frame["perennial_flag"] = _coalesce(frame, ["Depth_avg", "perennial_flag"])
    return _filter_geometry(frame, {"Polygon", "MultiPolygon"})


def _normalize_water_overture(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["id", "fid"]))
    frame["name"] = _coalesce(frame, ["name", "names.primary", "names_primary"])
    frame["fclass"] = _stringify(_coalesce(frame, ["class", "subtype"], default="water"))
    frame["water_ty"] = _stringify(_coalesce(frame, ["type", "subtype"], default="water"))
    frame["feature_kind"] = _geometry_feature_kind(frame)
    frame["water_class"] = _stringify(_coalesce(frame, ["class", "subtype"], default="water"))
    frame["perennial_flag"] = _coalesce(frame, ["perennial_flag"])
    return _filter_geometry(frame, {"LineString", "MultiLineString", "Polygon", "MultiPolygon"})


def _normalize_waterways_osm(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["osm_id", "id", "objectid", "fid"]))
    frame["name"] = _coalesce(frame, ["name", "waterway", "fclass"])
    frame["name_en"] = _coalesce(frame, ["name_en", "name"])
    frame["name_ur"] = _coalesce(frame, ["name_ur", "name"])
    frame["fclass"] = _stringify(_coalesce(frame, ["waterway", "fclass"], default="river"))
    frame["water_ty"] = "line"
    frame["feature_kind"] = pd.Series(["line"] * len(frame), index=frame.index, dtype="object")
    frame["water_class"] = frame["fclass"]
    return _filter_geometry(frame, {"LineString", "MultiLineString"})


def _normalize_waterways_local_osm_like(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    return _normalize_waterways_osm(frame, geohash_precision=geohash_precision)


def _normalize_waterways_hydrorivers(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    del geohash_precision
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["HYRIV_ID", "river_id", "id"]))
    frame["name"] = _coalesce(frame, ["name", "River_name", "river_name"])
    frame["name_en"] = _coalesce(frame, ["name_en", "name"])
    frame["name_ur"] = _coalesce(frame, ["name_ur", "name"])
    frame["fclass"] = _stringify(_coalesce(frame, ["fclass"], default="river"))
    frame["water_ty"] = "line"
    frame["feature_kind"] = pd.Series(["line"] * len(frame), index=frame.index, dtype="object")
    frame["water_class"] = _stringify(_coalesce(frame, ["ORD_STRA", "fclass"], default="river"))
    frame["perennial_flag"] = _coalesce(frame, ["DIS_AV_CMS", "perennial_flag"])
    return _filter_geometry(frame, {"LineString", "MultiLineString"})


def _normalize_poi_osm(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["osm_id", "id", "objectid", "fid"]))
    frame["name"] = _coalesce(frame, ["name", "alt_name"])
    frame["name_alt"] = _coalesce(frame, ["alt_name", "name_en"])
    frame["category"] = _stringify(_coalesce(frame, ["fclass", "amenity", "type", "class"], default="poi"))
    frame["admin_country"] = _coalesce(frame, ["admin_country", "country", "addr:country", "iso3166-1"])
    frame = _ensure_point_geometry(frame)
    frame["GeoHash"] = _ensure_geohash(frame, precision=geohash_precision)
    return frame


def _normalize_poi_gns(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["ufi", "uni", "id"]))
    frame["name"] = _coalesce(frame, ["full_name", "full_nm_nd", "name", "display"])
    frame["name_alt"] = _coalesce(frame, ["full_nm_nd", "generic"])
    frame["category"] = _stringify(_coalesce(frame, ["desig_cd", "fc", "type"], default="poi"))
    admin_country = _stringify(_coalesce(frame, ["CC1", "cc1", "country", "admin_country", "cc_ft", "cc_nm"]))
    frame["admin_country"] = admin_country.str.split(",").str[0]
    frame = _ensure_point_geometry(frame)
    frame["GeoHash"] = _ensure_geohash(frame, precision=geohash_precision)
    return frame


def _normalize_poi_google(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["place_id", "id", "sourceid", "name"]))
    display_name = _coalesce(frame, ["displayName.text", "display_name"])
    raw_name = _coalesce(frame, ["name"])
    resource_name = raw_name.apply(lambda value: str(value).strip() if _is_google_places_resource_name(value) else pd.NA)
    frame["name"] = display_name.where(~display_name.apply(_is_missing), raw_name.where(resource_name.apply(_is_missing), pd.NA))
    frame["name_alt"] = _coalesce(frame, ["formatted_address", "formattedAddress", "vicinity"])
    frame["name_alt"] = frame["name_alt"].where(~frame["name_alt"].apply(_is_missing), resource_name)
    category = _coalesce(frame, ["category", "primary_type", "primaryType", "type", "types"], default="poi")
    frame["category"] = _stringify(category).apply(_first_google_poi_category)
    frame["admin_country"] = _coalesce(frame, ["country", "admin_country", "region_code"])
    frame = _ensure_point_geometry(frame)
    frame["GeoHash"] = _ensure_geohash(frame, precision=geohash_precision)
    return frame


def _is_google_places_resource_name(value: object) -> bool:
    return isinstance(value, str) and value.strip().startswith("places/")


def _first_google_poi_category(value: object) -> str:
    text = str(value or "").strip()
    if not text or text == "<NA>":
        return "poi"
    if text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list) and parsed:
                return str(parsed[0])
        except Exception:  # noqa: BLE001
            pass
    return text.split(",")[0].strip() or "poi"


def _normalize_poi_rh(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["id", "sourceid"]))
    frame["name"] = _coalesce(frame, ["name", "alternaten"])
    frame["name_alt"] = _coalesce(frame, ["alternaten"])
    frame["category"] = _stringify(_coalesce(frame, ["type", "class", "label"], default="poi"))
    frame["admin_country"] = _coalesce(frame, ["country", "admin_country"])
    frame = _ensure_point_geometry(frame)
    frame["GeoHash"] = _ensure_geohash(frame, precision=geohash_precision)
    return frame


def _normalize_poi_overture(frame: gpd.GeoDataFrame, *, geohash_precision: int) -> gpd.GeoDataFrame:
    frame["source_feature_id"] = _stringify(_coalesce(frame, ["id", "sourceid"]))
    frame["name"] = _coalesce(frame, ["name", "names.primary", "names_primary"])
    frame["name_alt"] = _coalesce(frame, ["brand"])
    frame["category"] = _stringify(_coalesce(frame, ["category", "class", "type"], default="poi"))
    frame["admin_country"] = _coalesce(frame, ["country", "admin_country"])
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
    "fields.water.osm_line": _normalize_water_osm_line,
    "fields.water.local_reference": _normalize_water_local_reference,
    "fields.water.hydrorivers_line": _normalize_water_hydrorivers,
    "fields.water.hydrolakes_polygon": _normalize_water_hydrolakes,
    "fields.water.overture": _normalize_water_overture,
    "fields.waterways.osm": _normalize_waterways_osm,
    "fields.waterways.local_osm_like": _normalize_waterways_local_osm_like,
    "fields.waterways.hydrorivers": _normalize_waterways_hydrorivers,
    "fields.poi.osm": _normalize_poi_osm,
    "fields.poi.gns": _normalize_poi_gns,
    "fields.poi.google": _normalize_poi_google,
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


def _numeric_coalesce(frame: gpd.GeoDataFrame, columns: list[str], default: object = pd.NA) -> pd.Series:
    return pd.to_numeric(_coalesce(frame, columns, default=default), errors="coerce")


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


def _geometry_feature_kind(frame: gpd.GeoDataFrame) -> pd.Series:
    kinds: list[str] = []
    for geometry_type in frame.geometry.geom_type.tolist():
        value = str(geometry_type or "").lower()
        if "polygon" in value:
            kinds.append("polygon")
        elif "line" in value:
            kinds.append("line")
        elif "point" in value:
            kinds.append("point")
        else:
            kinds.append("")
    return pd.Series(kinds, index=frame.index, dtype="object")


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
