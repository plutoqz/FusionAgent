from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CanonicalField:
    name: str
    meaning: str
    required: bool = True
    value_type: str = "string"


@dataclass(frozen=True)
class SourceFieldProfile:
    profile_id: str
    theme: str
    canonical_fields: dict[str, CanonicalField]
    provider_probe_order: dict[str, list[str]]
    expected_null_rates: dict[str, float] = field(default_factory=dict)
    country_overrides: dict[str, "SourceFieldProfileOverride"] = field(default_factory=dict)


@dataclass(frozen=True)
class SourceFieldProfileOverride:
    profile_id_suffix: str
    provider_probe_order: dict[str, list[str]] = field(default_factory=dict)
    expected_null_rates: dict[str, float] = field(default_factory=dict)


def _field(name: str, meaning: str, *, required: bool = True, value_type: str = "string") -> CanonicalField:
    return CanonicalField(name=name, meaning=meaning, required=required, value_type=value_type)


BUILDING_FIELDS = {
    "source_feature_id": _field("source_feature_id", "stable upstream feature identifier"),
    "height_m": _field("height_m", "building height in meters", required=False, value_type="float"),
    "name": _field("name", "building name", required=False),
    "building_class": _field("building_class", "building class or usage", required=False),
    "confidence": _field("confidence", "source confidence score", required=False, value_type="float"),
}

ROAD_FIELDS = {
    "source_feature_id": _field("source_feature_id", "stable upstream road feature identifier"),
    "road_class": _field("road_class", "road class used for fusion priority"),
    "name": _field("name", "road name", required=False),
    "surface": _field("surface", "road surface material", required=False),
    "lanes": _field("lanes", "lane count", required=False),
}

WATER_FIELDS = {
    "source_feature_id": _field("source_feature_id", "stable upstream water feature identifier"),
    "feature_kind": _field("feature_kind", "line or polygon water feature kind"),
    "water_class": _field("water_class", "water classification"),
    "name": _field("name", "water feature name", required=False),
    "perennial_flag": _field("perennial_flag", "perennial or flow/depth indicator", required=False),
}

WATERWAYS_FIELDS = {
    "source_feature_id": _field("source_feature_id", "stable upstream waterways feature identifier"),
    "feature_kind": _field("feature_kind", "waterways feature kind"),
    "water_class": _field("water_class", "waterways classification"),
    "name": _field("name", "waterways feature name", required=False),
    "name_en": _field("name_en", "English waterways feature name", required=False),
    "name_ur": _field("name_ur", "Urdu waterways feature name", required=False),
}

POI_FIELDS = {
    "source_feature_id": _field("source_feature_id", "stable upstream POI identifier"),
    "name": _field("name", "primary POI name"),
    "name_alt": _field("name_alt", "alternate POI name", required=False),
    "category": _field("category", "POI category or designation"),
    "admin_country": _field("admin_country", "admin country code", required=False),
    "GeoHash": _field("GeoHash", "geohash used for bounded neighbor matching", required=False),
}


_REFERENCE_BUILDING_PROBES = {
    "source_feature_id": ["id", "quadkey", "sourceid", "OBJECTID", "objectid", "fid"],
    "height_m": ["height", "Height", "HEIGHT", "building_h", "bld_h"],
    "name": ["name", "Name"],
    "building_class": ["type", "class", "CATEGORY"],
    "confidence": ["confidence", "probability", "prob"],
}


PROFILES: dict[str, SourceFieldProfile] = {
    "fields.building.osm": SourceFieldProfile(
        profile_id="fields.building.osm",
        theme="building",
        canonical_fields=BUILDING_FIELDS,
        provider_probe_order={
            "source_feature_id": ["osm_id", "osm_way_id", "osm_rel_id", "id", "objectid", "fid"],
            "height_m": ["height", "Height", "HEIGHT", "building_h", "bld_h"],
            "name": ["name", "bld_name", "building_n"],
            "building_class": ["building", "type", "class", "use"],
            "confidence": ["confidence"],
        },
    ),
    "fields.building.microsoft": SourceFieldProfile(
        profile_id="fields.building.microsoft",
        theme="building",
        canonical_fields=BUILDING_FIELDS,
        provider_probe_order=_REFERENCE_BUILDING_PROBES,
    ),
    "fields.building.google": SourceFieldProfile(
        profile_id="fields.building.google",
        theme="building",
        canonical_fields=BUILDING_FIELDS,
        provider_probe_order=_REFERENCE_BUILDING_PROBES,
    ),
    "fields.building.openbuildingmap": SourceFieldProfile(
        profile_id="fields.building.openbuildingmap",
        theme="building",
        canonical_fields=BUILDING_FIELDS,
        provider_probe_order=_REFERENCE_BUILDING_PROBES,
    ),
    "fields.building.google_open_buildings_vector": SourceFieldProfile(
        profile_id="fields.building.google_open_buildings_vector",
        theme="building",
        canonical_fields=BUILDING_FIELDS,
        provider_probe_order=_REFERENCE_BUILDING_PROBES,
    ),
    "fields.road.osm": SourceFieldProfile(
        profile_id="fields.road.osm",
        theme="road",
        canonical_fields=ROAD_FIELDS,
        provider_probe_order={
            "source_feature_id": ["osm_id", "id", "objectid", "fid"],
            "road_class": ["road_class", "fclass", "highway", "class"],
            "name": ["name", "ref"],
            "surface": ["surface"],
            "lanes": ["lanes"],
        },
        expected_null_rates={"name": 0.80},
        country_overrides={
            "npl": SourceFieldProfileOverride(
                profile_id_suffix="npl",
                expected_null_rates={"name": 0.95},
            ),
        },
    ),
    "fields.road.overture_transportation": SourceFieldProfile(
        profile_id="fields.road.overture_transportation",
        theme="road",
        canonical_fields=ROAD_FIELDS,
        provider_probe_order={
            "source_feature_id": ["id", "segment_id", "road_id", "fid"],
            "road_class": ["road_class", "class", "subclass", "subtype", "type"],
            "name": ["name", "names.primary", "names_primary", "primary_name", "ref"],
            "surface": ["surface"],
            "lanes": ["lane_count", "lanes"],
        },
        expected_null_rates={"name": 0.85},
        country_overrides={
            "npl": SourceFieldProfileOverride(
                profile_id_suffix="npl",
                expected_null_rates={"name": 0.98},
            ),
        },
    ),
    "fields.water.osm_polygon": SourceFieldProfile(
        profile_id="fields.water.osm_polygon",
        theme="water",
        canonical_fields=WATER_FIELDS,
        provider_probe_order={
            "source_feature_id": ["osm_id", "id", "objectid", "fid"],
            "feature_kind": ["geometry_type"],
            "water_class": ["water_class", "fclass", "natural", "waterway"],
            "name": ["name", "waterway", "natural"],
            "perennial_flag": ["perennial_flag", "perennial"],
        },
    ),
    "fields.water.local_reference": SourceFieldProfile(
        profile_id="fields.water.local_reference",
        theme="water",
        canonical_fields=WATER_FIELDS,
        provider_probe_order={
            "source_feature_id": ["Hylak_id", "lake_id", "id", "OBJECTID", "fid"],
            "feature_kind": ["geometry_type"],
            "water_class": ["Lake_type", "type", "class", "fclass"],
            "name": ["Lake_name", "name", "Name"],
            "perennial_flag": ["perennial_flag", "Depth_avg"],
        },
    ),
    "fields.water.hydrorivers_line": SourceFieldProfile(
        profile_id="fields.water.hydrorivers_line",
        theme="water",
        canonical_fields=WATER_FIELDS,
        provider_probe_order={
            "source_feature_id": ["HYRIV_ID", "river_id", "id"],
            "feature_kind": ["line"],
            "water_class": ["ORD_STRA", "fclass"],
            "name": ["name", "River_name", "river_name"],
            "perennial_flag": ["DIS_AV_CMS", "perennial_flag"],
        },
    ),
    "fields.water.hydrolakes_polygon": SourceFieldProfile(
        profile_id="fields.water.hydrolakes_polygon",
        theme="water",
        canonical_fields=WATER_FIELDS,
        provider_probe_order={
            "source_feature_id": ["Hylak_id", "lake_id", "id"],
            "feature_kind": ["polygon"],
            "water_class": ["Lake_type", "fclass"],
            "name": ["Lake_name", "name", "Name"],
            "perennial_flag": ["Depth_avg", "perennial_flag"],
        },
    ),
    "fields.water.overture": SourceFieldProfile(
        profile_id="fields.water.overture",
        theme="water",
        canonical_fields=WATER_FIELDS,
        provider_probe_order={
            "source_feature_id": ["id", "fid"],
            "feature_kind": ["subtype"],
            "water_class": ["class", "subtype"],
            "name": ["name", "names.primary", "names_primary"],
            "perennial_flag": ["perennial_flag"],
        },
    ),
    "fields.waterways.osm": SourceFieldProfile(
        profile_id="fields.waterways.osm",
        theme="waterways",
        canonical_fields=WATERWAYS_FIELDS,
        provider_probe_order={
            "source_feature_id": ["osm_id", "id", "objectid", "fid"],
            "feature_kind": ["line"],
            "water_class": ["waterway", "fclass"],
            "name": ["name", "waterway", "fclass"],
            "name_en": ["name_en", "name"],
            "name_ur": ["name_ur", "name"],
        },
    ),
    "fields.waterways.local_osm_like": SourceFieldProfile(
        profile_id="fields.waterways.local_osm_like",
        theme="waterways",
        canonical_fields=WATERWAYS_FIELDS,
        provider_probe_order={
            "source_feature_id": ["osm_id", "id", "objectid", "fid"],
            "feature_kind": ["line"],
            "water_class": ["waterway", "fclass"],
            "name": ["name", "waterway", "fclass"],
            "name_en": ["name_en", "name"],
            "name_ur": ["name_ur", "name"],
        },
    ),
    "fields.waterways.hydrorivers": SourceFieldProfile(
        profile_id="fields.waterways.hydrorivers",
        theme="waterways",
        canonical_fields=WATERWAYS_FIELDS,
        provider_probe_order={
            "source_feature_id": ["HYRIV_ID", "river_id", "id"],
            "feature_kind": ["line"],
            "water_class": ["ORD_STRA", "fclass"],
            "name": ["name", "River_name", "river_name"],
            "name_en": ["name_en", "name"],
            "name_ur": ["name_ur", "name"],
        },
    ),
    "fields.poi.osm": SourceFieldProfile(
        profile_id="fields.poi.osm",
        theme="poi",
        canonical_fields=POI_FIELDS,
        provider_probe_order={
            "source_feature_id": ["osm_id", "id", "objectid", "fid"],
            "name": ["name", "alt_name"],
            "name_alt": ["alt_name", "name_en"],
            "category": ["fclass", "amenity", "type", "class"],
            "admin_country": ["admin_country", "country", "addr:country", "iso3166-1"],
            "GeoHash": ["GeoHash", "geohash"],
        },
    ),
    "fields.poi.gns": SourceFieldProfile(
        profile_id="fields.poi.gns",
        theme="poi",
        canonical_fields=POI_FIELDS,
        provider_probe_order={
            "source_feature_id": ["ufi", "uni", "id", "UFI", "UNI"],
            "name": ["full_name", "full_nm_nd", "name", "display", "FULL_NAME"],
            "name_alt": ["full_nm_nd", "generic"],
            "category": ["desig_cd", "fc", "type", "DSG"],
            "admin_country": ["CC1", "cc1", "country", "admin_country", "cc_ft", "cc_nm"],
            "GeoHash": ["GeoHash", "geohash"],
        },
    ),
    "fields.poi.rh": SourceFieldProfile(
        profile_id="fields.poi.rh",
        theme="poi",
        canonical_fields=POI_FIELDS,
        provider_probe_order={
            "source_feature_id": ["id", "sourceid", "ID"],
            "name": ["name", "NAME", "alternaten"],
            "name_alt": ["alternaten"],
            "category": ["type", "class", "label", "CATEGORY"],
            "admin_country": ["admin_country", "country"],
            "GeoHash": ["GeoHash", "geohash"],
        },
    ),
    "fields.poi.overture_places": SourceFieldProfile(
        profile_id="fields.poi.overture_places",
        theme="poi",
        canonical_fields=POI_FIELDS,
        provider_probe_order={
            "source_feature_id": ["id", "sourceid"],
            "name": ["name", "names.primary", "names_primary"],
            "name_alt": ["brand"],
            "category": ["category", "categories.primary", "class", "type"],
            "admin_country": ["admin_country", "country"],
            "GeoHash": ["GeoHash", "geohash"],
        },
    ),
}

_COUNTRY_CODE_ALIASES = {
    "np": "npl",
}


class SourceFieldProfileRegistry:
    def __init__(self, profiles: dict[str, SourceFieldProfile] | None = None) -> None:
        self._profiles = dict(profiles or PROFILES)

    def get(self, profile_id: str) -> SourceFieldProfile:
        try:
            return _copy_profile(self._profiles[profile_id])
        except KeyError as exc:
            raise KeyError(f"Unknown source field mapping profile={profile_id}") from exc

    def resolve(self, profile_id: str, *, country_code: str | None = None) -> SourceFieldProfile:
        profile = self.get(profile_id)
        normalized_country = _normalize_country_code(country_code)
        override = profile.country_overrides.get(normalized_country)
        if override is None:
            return profile

        provider_probe_order = _copy_provider_probe_order(profile.provider_probe_order)
        provider_probe_order.update(_copy_provider_probe_order(override.provider_probe_order))
        expected_null_rates = {
            **profile.expected_null_rates,
            **override.expected_null_rates,
        }
        return SourceFieldProfile(
            profile_id=f"{profile.profile_id}.{override.profile_id_suffix}",
            theme=profile.theme,
            canonical_fields=profile.canonical_fields,
            provider_probe_order=provider_probe_order,
            expected_null_rates=expected_null_rates,
            country_overrides=profile.country_overrides,
        )

    def profile_ids_for_theme(self, theme: str) -> list[str]:
        requested = theme.strip().lower()
        return sorted(profile_id for profile_id, profile in self._profiles.items() if profile.theme == requested)


def _normalize_country_code(country_code: str | None) -> str:
    token = str(country_code or "").strip().casefold()
    return _COUNTRY_CODE_ALIASES.get(token, token)


def _copy_provider_probe_order(provider_probe_order: dict[str, list[str]]) -> dict[str, list[str]]:
    return {field: list(probes) for field, probes in provider_probe_order.items()}


def _copy_profile(profile: SourceFieldProfile) -> SourceFieldProfile:
    return SourceFieldProfile(
        profile_id=profile.profile_id,
        theme=profile.theme,
        canonical_fields=dict(profile.canonical_fields),
        provider_probe_order=_copy_provider_probe_order(profile.provider_probe_order),
        expected_null_rates=dict(profile.expected_null_rates),
        country_overrides=dict(profile.country_overrides),
    )
