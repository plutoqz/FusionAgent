from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

from kg.models import DataSourceNode


DEFAULT_DISASTER_TYPES = ["generic", "flood", "earthquake", "typhoon"]


@dataclass(frozen=True)
class CatalogBundleSpec:
    source_id: str
    osm_source_id: str
    ref_source_id: Optional[str]
    bundle_strategy: str

    @property
    def component_source_ids(self) -> Tuple[str, ...]:
        if self.ref_source_id is None:
            return (self.osm_source_id,)
        return (self.osm_source_id, self.ref_source_id)


@dataclass(frozen=True)
class RawVectorSourceSpec:
    source_id: str
    locator_kind: str
    relative_path: Tuple[str, ...]
    glob_pattern: Optional[str] = None

    @property
    def path_hint(self) -> str:
        prefix = "/".join(self.relative_path)
        if self.glob_pattern:
            return f"{prefix}/{self.glob_pattern}"
        return prefix


RAW_VECTOR_SOURCE_SPECS: Tuple[RawVectorSourceSpec, ...] = (
    RawVectorSourceSpec(
        source_id="raw.osm.building",
        locator_kind="first_shp_in_dir",
        relative_path=("Data", "buildings", "OSM"),
    ),
    RawVectorSourceSpec(
        source_id="raw.google.building",
        locator_kind="first_shp_in_dir",
        relative_path=("Data", "buildings", "Google"),
    ),
    RawVectorSourceSpec(
        source_id="raw.microsoft.building",
        locator_kind="first_shp_in_dir",
        relative_path=("Data", "buildings", "Microsoft"),
    ),
    RawVectorSourceSpec(
        source_id="raw.osm.road",
        locator_kind="first_shp_in_dir",
        relative_path=("Data", "roads", "OSM"),
    ),
    RawVectorSourceSpec(
        source_id="raw.osm.water",
        locator_kind="exact_path",
        relative_path=("Data", "burundi-260127-free.shp", "gis_osm_water_a_free_1.shp"),
    ),
    RawVectorSourceSpec(
        source_id="raw.local.water",
        locator_kind="first_shp_in_dir",
        relative_path=("Data", "water"),
    ),
    RawVectorSourceSpec(
        source_id="raw.osm.poi",
        locator_kind="exact_path",
        relative_path=("Data", "burundi-260127-free.shp", "gis_osm_pois_free_1.shp"),
    ),
    RawVectorSourceSpec(
        source_id="raw.gns.poi",
        locator_kind="recursive_glob",
        relative_path=("Data", "POI"),
        glob_pattern="**/GNS.shp",
    ),
    RawVectorSourceSpec(
        source_id="raw.rh.poi",
        locator_kind="recursive_glob",
        relative_path=("Data", "POI"),
        glob_pattern="**/RH.shp",
    ),
)

RAW_VECTOR_SOURCE_SPECS_BY_ID = {spec.source_id: spec for spec in RAW_VECTOR_SOURCE_SPECS}

CATALOG_BUNDLE_SPECS: Tuple[CatalogBundleSpec, ...] = (
    CatalogBundleSpec(
        source_id="catalog.flood.building",
        osm_source_id="raw.osm.building",
        ref_source_id="raw.google.building",
        bundle_strategy="osm_ref_pair",
    ),
    CatalogBundleSpec(
        source_id="catalog.flood.road",
        osm_source_id="raw.osm.road",
        ref_source_id=None,
        bundle_strategy="single_source_with_empty_ref",
    ),
    CatalogBundleSpec(
        source_id="catalog.earthquake.building",
        osm_source_id="raw.osm.building",
        ref_source_id="raw.microsoft.building",
        bundle_strategy="osm_ref_pair",
    ),
    CatalogBundleSpec(
        source_id="catalog.earthquake.road",
        osm_source_id="raw.osm.road",
        ref_source_id=None,
        bundle_strategy="single_source_with_empty_ref",
    ),
    CatalogBundleSpec(
        source_id="catalog.typhoon.road",
        osm_source_id="raw.osm.road",
        ref_source_id=None,
        bundle_strategy="single_source_with_empty_ref",
    ),
)

CATALOG_BUNDLE_SPECS_BY_ID = {spec.source_id: spec for spec in CATALOG_BUNDLE_SPECS}


def get_raw_vector_source_spec(source_id: str) -> RawVectorSourceSpec:
    try:
        return RAW_VECTOR_SOURCE_SPECS_BY_ID[source_id]
    except KeyError as exc:
        raise KeyError(f"Unknown raw vector source: {source_id}") from exc


def get_catalog_bundle_spec(source_id: str) -> CatalogBundleSpec:
    try:
        return CATALOG_BUNDLE_SPECS_BY_ID[source_id]
    except KeyError as exc:
        raise KeyError(f"Unknown catalog bundle source: {source_id}") from exc


def _bundle_path_hints(bundle_spec: CatalogBundleSpec) -> List[str]:
    return [get_raw_vector_source_spec(source_id).path_hint for source_id in bundle_spec.component_source_ids]


def _raw_path_hint(source_id: str) -> str:
    return get_raw_vector_source_spec(source_id).path_hint


def _bundle_component_ids(source_id: str) -> List[str]:
    return list(get_catalog_bundle_spec(source_id).component_source_ids)


def _bundle_strategy(source_id: str) -> str:
    return get_catalog_bundle_spec(source_id).bundle_strategy


def build_data_sources() -> List[DataSourceNode]:
    return [
        DataSourceNode(
            source_id="upload.bundle",
            source_name="Uploaded Bundle",
            supported_types=["dt.building.bundle", "dt.road.bundle", "dt.raw.vector"],
            disaster_types=list(DEFAULT_DISASTER_TYPES),
            quality_score=1.0,
            source_kind="local_upload",
            quality_tier="operator_provided",
            freshness_category="request_bound",
            freshness_hours=0,
            freshness_score=1.0,
            supported_job_types=["building", "road"],
            supported_geometry_types=["mixed", "polygon", "line", "point"],
            metadata={
                "kind": "local",
                "provider_family": "manual_upload",
                "bundle_strategy": "operator_supplied",
            },
        ),
        DataSourceNode(
            source_id="catalog.flood.building",
            source_name="Flood Building Bundle (OSM + Google)",
            supported_types=["dt.building.bundle"],
            disaster_types=["flood", "generic"],
            quality_score=0.86,
            source_kind="catalog",
            quality_tier="curated",
            freshness_category="event_snapshot",
            freshness_hours=72,
            freshness_score=0.74,
            supported_job_types=["building"],
            supported_geometry_types=["polygon"],
            metadata={
                "kind": "catalog",
                "priority": 2,
                "provider_family": "local_bundle_catalog",
                "bundle_strategy": _bundle_strategy("catalog.flood.building"),
                "component_source_ids": _bundle_component_ids("catalog.flood.building"),
                "path_hints": _bundle_path_hints(get_catalog_bundle_spec("catalog.flood.building")),
                "supports_aoi": True,
                "materialization_scope": "resolved_aoi_clip",
            },
        ),
        DataSourceNode(
            source_id="catalog.earthquake.building",
            source_name="Earthquake Building Bundle (OSM + Microsoft)",
            supported_types=["dt.building.bundle"],
            disaster_types=["earthquake", "generic"],
            quality_score=0.88,
            source_kind="catalog",
            quality_tier="curated",
            freshness_category="event_snapshot",
            freshness_hours=96,
            freshness_score=0.71,
            supported_job_types=["building"],
            supported_geometry_types=["polygon"],
            metadata={
                "kind": "catalog",
                "priority": 2,
                "provider_family": "local_bundle_catalog",
                "bundle_strategy": _bundle_strategy("catalog.earthquake.building"),
                "component_source_ids": _bundle_component_ids("catalog.earthquake.building"),
                "path_hints": _bundle_path_hints(get_catalog_bundle_spec("catalog.earthquake.building")),
                "supports_aoi": True,
                "materialization_scope": "resolved_aoi_clip",
            },
        ),
        DataSourceNode(
            source_id="catalog.flood.road",
            source_name="Flood Road Bundle (OSM Baseline)",
            supported_types=["dt.road.bundle"],
            disaster_types=["flood", "generic"],
            quality_score=0.85,
            source_kind="catalog",
            quality_tier="curated",
            freshness_category="event_snapshot",
            freshness_hours=72,
            freshness_score=0.73,
            supported_job_types=["road"],
            supported_geometry_types=["line"],
            metadata={
                "kind": "catalog",
                "priority": 2,
                "provider_family": "local_bundle_catalog",
                "bundle_strategy": _bundle_strategy("catalog.flood.road"),
                "component_source_ids": _bundle_component_ids("catalog.flood.road"),
                "path_hints": _bundle_path_hints(get_catalog_bundle_spec("catalog.flood.road")),
                "supports_aoi": True,
                "materialization_scope": "resolved_aoi_clip",
            },
        ),
        DataSourceNode(
            source_id="catalog.earthquake.road",
            source_name="Earthquake Road Bundle (OSM Baseline)",
            supported_types=["dt.road.bundle"],
            disaster_types=["earthquake", "generic"],
            quality_score=0.84,
            source_kind="catalog",
            quality_tier="curated",
            freshness_category="event_snapshot",
            freshness_hours=96,
            freshness_score=0.69,
            supported_job_types=["road"],
            supported_geometry_types=["line"],
            metadata={
                "kind": "catalog",
                "priority": 2,
                "provider_family": "local_bundle_catalog",
                "bundle_strategy": _bundle_strategy("catalog.earthquake.road"),
                "component_source_ids": _bundle_component_ids("catalog.earthquake.road"),
                "path_hints": _bundle_path_hints(get_catalog_bundle_spec("catalog.earthquake.road")),
                "supports_aoi": True,
                "materialization_scope": "resolved_aoi_clip",
            },
        ),
        DataSourceNode(
            source_id="catalog.typhoon.road",
            source_name="Typhoon Road Bundle (OSM Baseline)",
            supported_types=["dt.road.bundle"],
            disaster_types=["typhoon", "generic"],
            quality_score=0.87,
            source_kind="catalog",
            quality_tier="curated",
            freshness_category="event_snapshot",
            freshness_hours=48,
            freshness_score=0.78,
            supported_job_types=["road"],
            supported_geometry_types=["line"],
            metadata={
                "kind": "catalog",
                "priority": 2,
                "provider_family": "local_bundle_catalog",
                "bundle_strategy": _bundle_strategy("catalog.typhoon.road"),
                "component_source_ids": _bundle_component_ids("catalog.typhoon.road"),
                "path_hints": _bundle_path_hints(get_catalog_bundle_spec("catalog.typhoon.road")),
                "supports_aoi": True,
                "materialization_scope": "resolved_aoi_clip",
            },
        ),
        DataSourceNode(
            source_id="raw.osm.building",
            source_name="OSM Building Footprints",
            supported_types=["dt.raw.vector"],
            disaster_types=list(DEFAULT_DISASTER_TYPES),
            quality_score=0.84,
            source_kind="open_data",
            quality_tier="community_curated",
            freshness_category="sample_snapshot",
            freshness_hours=168,
            freshness_score=0.62,
            supported_job_types=["building"],
            supported_geometry_types=["polygon"],
            metadata={
                "kind": "raw_vector",
                "provider_family": "osm",
                "theme": "building",
                "source_role": "osm_primary",
                "path_hint": _raw_path_hint("raw.osm.building"),
                "supports_aoi": True,
                "materialization_scope": "country_bundle_then_clip",
                "materialization_provider": "geofabrik",
            },
        ),
        DataSourceNode(
            source_id="raw.google.building",
            source_name="Google Open Buildings",
            supported_types=["dt.raw.vector"],
            disaster_types=list(DEFAULT_DISASTER_TYPES),
            quality_score=0.87,
            source_kind="open_data",
            quality_tier="foundation_model_extracted",
            freshness_category="sample_snapshot",
            freshness_hours=240,
            freshness_score=0.58,
            supported_job_types=["building"],
            supported_geometry_types=["polygon"],
            metadata={
                "kind": "raw_vector",
                "provider_family": "google",
                "theme": "building",
                "source_role": "reference_candidate",
                "path_hint": _raw_path_hint("raw.google.building"),
                "supports_aoi": False,
                "materialization_scope": "local_only",
            },
        ),
        DataSourceNode(
            source_id="raw.microsoft.building",
            source_name="Microsoft Building Footprints",
            supported_types=["dt.raw.vector"],
            disaster_types=list(DEFAULT_DISASTER_TYPES),
            quality_score=0.88,
            source_kind="open_data",
            quality_tier="provider_curated",
            freshness_category="sample_snapshot",
            freshness_hours=240,
            freshness_score=0.59,
            supported_job_types=["building"],
            supported_geometry_types=["polygon"],
            metadata={
                "kind": "raw_vector",
                "provider_family": "microsoft",
                "theme": "building",
                "source_role": "reference_candidate",
                "path_hint": _raw_path_hint("raw.microsoft.building"),
                "supports_aoi": True,
                "materialization_scope": "country_tiles_then_clip",
                "materialization_provider": "microsoft_global_buildings",
            },
        ),
        DataSourceNode(
            source_id="raw.osm.road",
            source_name="OSM Road Network",
            supported_types=["dt.raw.vector"],
            disaster_types=list(DEFAULT_DISASTER_TYPES),
            quality_score=0.82,
            source_kind="open_data",
            quality_tier="community_curated",
            freshness_category="sample_snapshot",
            freshness_hours=168,
            freshness_score=0.63,
            supported_job_types=["road"],
            supported_geometry_types=["line"],
            metadata={
                "kind": "raw_vector",
                "provider_family": "osm",
                "theme": "road",
                "source_role": "osm_primary",
                "path_hint": _raw_path_hint("raw.osm.road"),
                "supports_aoi": True,
                "materialization_scope": "country_bundle_then_clip",
                "materialization_provider": "geofabrik",
            },
        ),
        DataSourceNode(
            source_id="raw.osm.water",
            source_name="OSM Water Features",
            supported_types=["dt.raw.vector"],
            disaster_types=list(DEFAULT_DISASTER_TYPES),
            quality_score=0.8,
            source_kind="open_data",
            quality_tier="community_curated",
            freshness_category="sample_snapshot",
            freshness_hours=168,
            freshness_score=0.61,
            supported_job_types=["building", "road"],
            supported_geometry_types=["polygon", "line"],
            metadata={
                "kind": "raw_vector",
                "provider_family": "osm",
                "theme": "water",
                "source_role": "environmental_context",
                "path_hint": _raw_path_hint("raw.osm.water"),
                "supports_aoi": True,
                "materialization_scope": "country_bundle_then_clip",
                "materialization_provider": "geofabrik",
            },
        ),
        DataSourceNode(
            source_id="raw.local.water",
            source_name="Local Open Water Sample",
            supported_types=["dt.raw.vector"],
            disaster_types=list(DEFAULT_DISASTER_TYPES),
            quality_score=0.79,
            source_kind="open_data",
            quality_tier="local_sample",
            freshness_category="sample_snapshot",
            freshness_hours=240,
            freshness_score=0.55,
            supported_job_types=["building", "road"],
            supported_geometry_types=["polygon"],
            metadata={
                "kind": "raw_vector",
                "provider_family": "local_open_data",
                "theme": "water",
                "source_role": "environmental_context",
                "path_hint": _raw_path_hint("raw.local.water"),
                "supports_aoi": False,
                "materialization_scope": "local_only",
            },
        ),
        DataSourceNode(
            source_id="raw.osm.poi",
            source_name="OSM Points Of Interest",
            supported_types=["dt.raw.vector"],
            disaster_types=list(DEFAULT_DISASTER_TYPES),
            quality_score=0.78,
            source_kind="open_data",
            quality_tier="community_curated",
            freshness_category="sample_snapshot",
            freshness_hours=168,
            freshness_score=0.6,
            supported_job_types=["building", "road"],
            supported_geometry_types=["point", "polygon"],
            metadata={
                "kind": "raw_vector",
                "provider_family": "osm",
                "theme": "poi",
                "source_role": "enrichment_candidate",
                "path_hint": _raw_path_hint("raw.osm.poi"),
                "supports_aoi": True,
                "materialization_scope": "country_bundle_then_clip",
                "materialization_provider": "geofabrik",
            },
        ),
        DataSourceNode(
            source_id="raw.gns.poi",
            source_name="GNS Place Names",
            supported_types=["dt.raw.vector"],
            disaster_types=list(DEFAULT_DISASTER_TYPES),
            quality_score=0.81,
            source_kind="open_data",
            quality_tier="gazetteer",
            freshness_category="sample_snapshot",
            freshness_hours=720,
            freshness_score=0.42,
            supported_job_types=["building", "road"],
            supported_geometry_types=["point"],
            metadata={
                "kind": "raw_vector",
                "provider_family": "gns",
                "theme": "poi",
                "source_role": "name_reference",
                "path_hint": _raw_path_hint("raw.gns.poi"),
                "supports_aoi": False,
                "materialization_scope": "local_only",
            },
        ),
        DataSourceNode(
            source_id="raw.rh.poi",
            source_name="RH Points Of Interest",
            supported_types=["dt.raw.vector"],
            disaster_types=list(DEFAULT_DISASTER_TYPES),
            quality_score=0.76,
            source_kind="open_data",
            quality_tier="local_sample",
            freshness_category="sample_snapshot",
            freshness_hours=720,
            freshness_score=0.4,
            supported_job_types=["building", "road"],
            supported_geometry_types=["point"],
            metadata={
                "kind": "raw_vector",
                "provider_family": "rh",
                "theme": "poi",
                "source_role": "reference_candidate",
                "path_hint": _raw_path_hint("raw.rh.poi"),
                "supports_aoi": False,
                "materialization_scope": "local_only",
            },
        ),
    ]
