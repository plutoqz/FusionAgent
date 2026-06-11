from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Any, Iterable, Optional

import geopandas as gpd
import httpx
import pandas as pd
from shapely import wkt
from shapely.geometry import shape

from kg.source_catalog import get_raw_vector_source_spec
from services.aoi_resolution_service import ResolvedAOI
from utils.raster_cli import gdalinfo_json
from utils.shp_zip import collect_bundle_files, safe_extract_zip
from utils.vector_clip import BBox, clip_frame_to_request_bbox, frame_bbox_in_crs


GEOFABRIK_BURUNDI_SHP_URL = "https://download.geofabrik.de/africa/burundi-latest-free.shp.zip"
GEOFABRIK_INDEX_URL = "https://download.geofabrik.de/index-v1.json"
MSFT_BUILDING_DATASET_LINKS_URL = "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv"
GNS_DATA_INDEX_URL = "https://geonames.nga.mil/geonames/GNSData/data/data.json"
HYDRORIVERS_GLOBAL_ZIP_URL = "https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_shp.zip"
HYDROLAKES_GLOBAL_ZIP_URL = "https://data.hydrosheds.org/file/hydrolakes/HydroLAKES_polys_v10_shp.zip"
OVERTURE_DOWNLOAD_TIMEOUT_SECONDS = 600


_GEOFABRIK_LAYER_NAMES = {
    "raw.osm.building": "gis_osm_buildings_a_free_1.shp",
    "raw.osm.road": "gis_osm_roads_free_1.shp",
    "raw.osm.water": "gis_osm_water_a_free_1.shp",
    "raw.osm.waterways": "gis_osm_waterways_free_1.shp",
    "raw.osm.poi": "gis_osm_pois_free_1.shp",
}

_LOCAL_SOURCE_CANDIDATES = {
    "raw.osm.building": [
        ("Data", "buildings", "OSM"),
        ("Data", "burundi-260127-free.shp", "gis_osm_buildings_a_free_1.shp"),
    ],
    "raw.osm.road": [
        ("Data", "roads", "OSM"),
        ("Data", "burundi-260127-free.shp", "gis_osm_roads_free_1.shp"),
    ],
    "raw.overture.transportation": [
        ("Data", "roads", "Overture"),
    ],
    "raw.overture.road": [
        ("Data", "roads", "Overture"),
    ],
    "raw.osm.water": [
        ("Data", "burundi-260127-free.shp", "gis_osm_water_a_free_1.shp"),
    ],
    "raw.osm.waterways": [
        ("Data", "burundi-260127-free.shp", "gis_osm_waterways_free_1.shp"),
    ],
    "raw.local.pakistan.waterways": [
        ("Data", "water", "Pakistan_Waterways_Data.shp"),
        ("Data", "water"),
    ],
    "raw.local.water": [
        ("Data", "water", "布隆迪湖泊.shp"),
        ("Data", "water"),
    ],
    "raw.hydrorivers.water": [
        ("Data", "water", "BDI.shp"),
        ("Data", "water", "HydroRIVERS"),
        ("Data", "water", "HydroRIVERS_v10.shp"),
    ],
    "raw.hydrolakes.water": [
        ("Data", "water", "布隆迪湖泊.shp"),
        ("Data", "water", "HydroLAKES"),
        ("Data", "water", "HydroLAKES_polys_v10.shp"),
    ],
    "raw.osm.poi": [
        ("Data", "POI"),
        ("Data", "burundi-260127-free.shp", "gis_osm_pois_free_1.shp"),
    ],
    "raw.gns.poi": [
        ("Data", "POI"),
    ],
    "raw.rh.poi": [
        ("Data", "POI"),
    ],
    "raw.microsoft.building": [
        ("Data", "buildings", "Microsoft"),
    ],
    "raw.google.building": [
        ("Data", "buildings", "Google"),
    ],
}

_REMOTELY_MATERIALIZABLE_SOURCE_IDS = {
    "raw.osm.building",
    "raw.osm.road",
    "raw.osm.water",
    "raw.osm.waterways",
    "raw.osm.poi",
    "raw.google.building",
    "raw.google.open_buildings.vector",
    "raw.google.poi",
    "raw.microsoft.building",
    "raw.overture.transportation",
    "raw.overture.road",
    "raw.hydrorivers.water",
    "raw.hydrolakes.water",
    "raw.gns.poi",
}

_SOURCE_ID_ALIASES = {
    "raw.geonames.poi": "raw.gns.poi",
}
_LOCAL_VECTOR_GLOB_PATTERNS = ("*.shp", "*.gpkg")


def _canonical_source_id(source_id: str) -> str:
    return _SOURCE_ID_ALIASES.get(source_id, source_id)


def _local_vector_glob_patterns(pattern: str | None) -> tuple[str, ...]:
    if not pattern:
        return _LOCAL_VECTOR_GLOB_PATTERNS
    patterns = [pattern]
    if pattern.lower().endswith(".shp"):
        patterns.append(f"{pattern[:-4]}.gpkg")
    return tuple(patterns)


@dataclass(frozen=True)
class SourceAssetResolution:
    source_id: str
    path: Path
    source_mode: str
    cache_hit: bool
    version_token: str
    bbox: Optional[BBox] = None
    feature_count: Optional[int] = None


@dataclass(frozen=True)
class SourceCoverageStatus:
    source_id: str
    source_mode: str
    feature_count: int | None
    coverage_status: str
    path: Path | None = None
    error: str | None = None


def coverage_status_for_count(feature_count: int | None) -> str:
    if feature_count is None:
        return "unknown"
    if feature_count == 0:
        return "empty"
    return "available"


def classify_source_fault(
    *,
    source: dict[str, Any] | None = None,
    expected_crs: str | None = None,
    error: Exception | str | None = None,
) -> str:
    source = dict(source or {})
    source_crs = str(source.get("crs") or "").strip().upper()
    normalized_expected = str(expected_crs or "").strip().upper()
    if normalized_expected and source_crs and source_crs != normalized_expected:
        return "CRS_MISMATCH"

    text = str(error or "").strip().lower()
    if "crs mismatch" in text:
        return "CRS_MISMATCH"
    if "corrupt" in text or "corrupted" in text or "broken" in text or "badzipfile" in text:
        return "SOURCE_CORRUPTED"
    if (
        "no official coverage" in text
        or "official no coverage" in text
        or "outside coverage" in text
    ):
        return "NO_OFFICIAL_COVERAGE"
    if (
        "unauthorized" in text
        or "forbidden" in text
        or "401" in text
        or "403" in text
        or "permission" in text
        or "api key" in text
        or "credential" in text
    ):
        return "UNAUTHORIZED"
    if (
        "provider unavailable" in text
        or "service unavailable" in text
        or "503" in text
        or "upstream unavailable" in text
    ):
        return "PROVIDER_UNAVAILABLE"
    if (
        "timeout" in text
        or "timed out" in text
        or "connection" in text
        or "network" in text
        or "dns" in text
        or "temporary failure" in text
        or "unreachable" in text
    ):
        return "NETWORK_FAILED"
    if "no local or remote source asset path available" in text or "not found" in text or "missing" in text:
        return "SOURCE_MISSING"
    if source.get("path") in {None, ""}:
        return "SOURCE_MISSING"
    return "SOURCE_CORRUPTED"


@dataclass(frozen=True)
class _GeofabrikBundle:
    slug: str
    download_url: str
    boundary_geometry: Any | None = None


@dataclass(frozen=True)
class _GNSCountryFile:
    country_code: str
    country_name: str
    download_url: str


def _path_version_token(path: Path) -> str:
    if path.suffix.lower() == ".shp":
        files = collect_bundle_files(path)
    else:
        files = [path]
    payload = "|".join(f"{item.name}:{int(item.stat().st_mtime)}:{item.stat().st_size}" for item in files if item.exists())
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _is_usable_local_vector_path(path: Path) -> bool:
    if not path.exists():
        return False
    if path.suffix.lower() != ".shp":
        return path.is_file()
    bundle_suffixes = {item.suffix.lower() for item in collect_bundle_files(path)}
    return {".shp", ".shx", ".dbf"}.issubset(bundle_suffixes)


def _quadkey_to_tile(quadkey: str) -> tuple[int, int, int]:
    tile_x = 0
    tile_y = 0
    level = len(quadkey)
    for index, digit in enumerate(quadkey):
        bit = level - index - 1
        mask = 1 << bit
        if digit in {"1", "3"}:
            tile_x |= mask
        if digit in {"2", "3"}:
            tile_y |= mask
    return tile_x, tile_y, level


def _tile_bounds(tile_x: int, tile_y: int, zoom: int) -> BBox:
    scale = 2**zoom
    min_lon = tile_x / scale * 360.0 - 180.0
    max_lon = (tile_x + 1) / scale * 360.0 - 180.0

    def _mercator_to_lat(tile_row: int) -> float:
        value = math.pi * (1 - 2 * tile_row / scale)
        return math.degrees(math.atan(math.sinh(value)))

    max_lat = _mercator_to_lat(tile_y)
    min_lat = _mercator_to_lat(tile_y + 1)
    return (min_lon, min_lat, max_lon, max_lat)


def _quadkey_bounds(quadkey: str) -> BBox:
    return _tile_bounds(*_quadkey_to_tile(quadkey))


def _bbox_intersects(left: BBox, right: BBox) -> bool:
    return not (
        left[2] < right[0]
        or right[2] < left[0]
        or left[3] < right[1]
        or right[3] < left[1]
    )


def _slugify(value: str | None) -> str:
    text = "".join(character.lower() if character.isalnum() else "-" for character in str(value or ""))
    parts = [part for part in text.split("-") if part]
    return "-".join(parts) or "unknown"


def _normalize_match_hint(value: str | None) -> str:
    text = "".join(character.lower() if character.isalnum() else " " for character in str(value or ""))
    return " ".join(part for part in text.split() if part)


def _tokenize_match_hint(value: str | None) -> set[str]:
    normalized = _normalize_match_hint(value)
    if not normalized:
        return set()
    return {token for token in normalized.split() if len(token) >= 3}


def _feature_geometry(feature: dict[str, Any]) -> Any | None:
    geometry = feature.get("geometry")
    if not geometry:
        return None
    try:
        return shape(geometry)
    except Exception:  # noqa: BLE001
        return None


def _json_safe_vector_value(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return value


def _is_google_places_resource_name(value: Any) -> bool:
    return isinstance(value, str) and value.strip().startswith("places/")


def _nested_mapping_value(value: Any, *keys: str) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _bbox_cache_key(request_bbox: Optional[BBox]) -> str:
    if request_bbox is None:
        return "full"
    return hashlib.sha1(repr(tuple(request_bbox)).encode("utf-8")).hexdigest()[:12]


def _url_list_cache_key(urls: Iterable[str]) -> str:
    normalized = "\n".join(sorted(str(url).strip() for url in urls if str(url).strip()))
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def _normalize_country_code(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def _normalize_country_name(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text.casefold() or None


def _filter_polygonal_frame(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if frame.empty:
        return frame
    filtered = frame[frame.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    if filtered.empty:
        return frame.iloc[0:0].copy()
    return filtered


class SourceAssetService:
    def __init__(
        self,
        *,
        repo_root: Path,
        cache_dir: Path,
        geofabrik_burundi_url: str = GEOFABRIK_BURUNDI_SHP_URL,
        geofabrik_index_url: str = GEOFABRIK_INDEX_URL,
        msft_dataset_links_url: str = MSFT_BUILDING_DATASET_LINKS_URL,
        gns_data_index_url: str = GNS_DATA_INDEX_URL,
        overture_transportation_url: str | None = None,
        google_open_buildings_urls: list[str] | None = None,
        google_places_api_key: str | None = None,
        google_places_cache_key: str | None = None,
        google_poi_authorization_path: Path | None = None,
        google_places_fetcher: object | None = None,
        hydrorivers_global_zip_url: str = HYDRORIVERS_GLOBAL_ZIP_URL,
        hydrolakes_global_zip_url: str = HYDROLAKES_GLOBAL_ZIP_URL,
        prefer_local_data: bool = True,
        http_max_retries: int = 3,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.geofabrik_burundi_url = geofabrik_burundi_url
        self.geofabrik_index_url = geofabrik_index_url
        self.msft_dataset_links_url = msft_dataset_links_url
        self.gns_data_index_url = gns_data_index_url
        self.overture_transportation_url = overture_transportation_url
        self.google_open_buildings_urls = list(google_open_buildings_urls or [])
        self.google_places_api_key = google_places_api_key
        self.google_places_cache_key = google_places_cache_key
        self.google_poi_authorization_path = Path(google_poi_authorization_path) if google_poi_authorization_path else None
        self.google_places_fetcher = google_places_fetcher
        self.hydrorivers_global_zip_url = hydrorivers_global_zip_url
        self.hydrolakes_global_zip_url = hydrolakes_global_zip_url
        self.prefer_local_data = prefer_local_data
        self.http_max_retries = max(1, int(http_max_retries))
        self._geofabrik_index_cache: list[dict[str, Any]] | None = None
        self._gns_download_index_cache: list[_GNSCountryFile] | None = None

    def can_materialize(self, source_id: str) -> bool:
        source_id = _canonical_source_id(source_id)
        if source_id in _REMOTELY_MATERIALIZABLE_SOURCE_IDS or source_id in _LOCAL_SOURCE_CANDIDATES:
            return True
        try:
            get_raw_vector_source_spec(source_id)
        except KeyError:
            return False
        return True

    def inspect_local_raster_profile(self, source_id: str, path: Path) -> dict[str, object]:
        info = gdalinfo_json(path)
        bands = info.get("bands", [])
        band_count = len(bands) if isinstance(bands, list) else 0
        return {
            "source_id": source_id,
            "path": str(path),
            "source_form": "raster",
            "runtime_status": "reservation_only",
            "band_count": band_count,
        }

    def resolve_raw_source_path(
        self,
        source_id: str,
        *,
        request_bbox: Optional[BBox] = None,
        aoi: ResolvedAOI | None = None,
    ) -> SourceAssetResolution:
        source_id = _canonical_source_id(source_id)
        effective_bbox = request_bbox or (tuple(aoi.bbox) if aoi is not None else None)

        if source_id == "raw.google.poi":
            return self._resolve_google_poi(request_bbox=effective_bbox, aoi=aoi)

        if self.prefer_local_data:
            local_path = self._try_local_path(source_id)
            if local_path is None:
                local_path = self._try_spec_local_path(source_id, aoi=aoi)
            if local_path is not None:
                local_resolution = self._build_local_resolution(
                    source_id,
                    local_path=local_path,
                    request_bbox=effective_bbox,
                )
                if local_resolution.feature_count != 0 or source_id not in _REMOTELY_MATERIALIZABLE_SOURCE_IDS:
                    return local_resolution

        if source_id in _GEOFABRIK_LAYER_NAMES:
            return self._resolve_geofabrik_source(source_id, request_bbox=effective_bbox, aoi=aoi)

        if source_id == "raw.microsoft.building":
            return self._resolve_msft_buildings(request_bbox=effective_bbox, aoi=aoi)
        if source_id in {"raw.google.building", "raw.google.open_buildings.vector"}:
            return self._resolve_google_open_buildings(source_id, request_bbox=effective_bbox)
        if source_id in {"raw.overture.transportation", "raw.overture.road"}:
            return self._resolve_overture_transportation(source_id=source_id, request_bbox=effective_bbox)
        if source_id in {"raw.hydrorivers.water", "raw.hydrolakes.water"}:
            return self._resolve_hydrosheds_water(source_id, request_bbox=effective_bbox)
        if source_id == "raw.gns.poi":
            return self._resolve_gns_poi(request_bbox=effective_bbox, aoi=aoi)

        raise FileNotFoundError(f"No local or remote source asset path available for {source_id}")

    def resolve_country_boundary(self, aoi: ResolvedAOI | None) -> gpd.GeoDataFrame | None:
        if aoi is None or (aoi.country_name is None and aoi.country_code is None):
            return None
        bundle = self._select_geofabrik_bundle(aoi)
        if bundle.boundary_geometry is None or bundle.boundary_geometry.is_empty:
            return None
        return gpd.GeoDataFrame(
            {"country_name": [aoi.country_name or bundle.slug]},
            geometry=[bundle.boundary_geometry],
            crs="EPSG:4326",
        )

    def _build_local_resolution(
        self,
        source_id: str,
        *,
        local_path: Path,
        request_bbox: Optional[BBox],
    ) -> SourceAssetResolution:
        if request_bbox is None:
            bbox, feature_count = self._inspect_vector_path(local_path)
            return SourceAssetResolution(
                source_id=source_id,
                path=local_path,
                source_mode="local_data",
                cache_hit=True,
                version_token=_path_version_token(local_path),
                bbox=bbox,
                feature_count=feature_count,
            )

        target_dir = self.cache_dir / "local_clips" / source_id.replace(".", "_") / _bbox_cache_key(request_bbox)
        clipped_path, cache_hit, bbox, feature_count = self._materialize_clipped_vector(
            source_path=local_path,
            target_dir=target_dir,
            request_bbox=request_bbox,
        )
        return SourceAssetResolution(
            source_id=source_id,
            path=clipped_path,
            source_mode="coverage_empty" if feature_count == 0 else "local_data_clipped",
            cache_hit=cache_hit,
            version_token=_path_version_token(local_path),
            bbox=bbox,
            feature_count=feature_count,
        )

    def _try_local_path(self, source_id: str) -> Optional[Path]:
        for rel_parts in _LOCAL_SOURCE_CANDIDATES.get(source_id, []):
            candidate = self.repo_root.joinpath(*rel_parts)
            if not candidate.exists():
                continue
            if candidate.is_dir():
                for pattern in _LOCAL_VECTOR_GLOB_PATTERNS:
                    matches = sorted(candidate.glob(pattern))
                    for match in matches:
                        if _is_usable_local_vector_path(match):
                            return match
                continue
            if _is_usable_local_vector_path(candidate):
                return candidate
        return None

    def _try_spec_local_path(self, source_id: str, *, aoi: ResolvedAOI | None) -> Optional[Path]:
        try:
            spec = get_raw_vector_source_spec(source_id)
        except KeyError:
            return None

        base_path = self.repo_root.joinpath(*spec.relative_path)
        if spec.locator_kind == "exact_path":
            if _is_usable_local_vector_path(base_path):
                return base_path
            return None

        if spec.locator_kind == "first_shp_in_dir":
            if not base_path.exists():
                return None
            matches = [
                path
                for pattern in _LOCAL_VECTOR_GLOB_PATTERNS
                for path in sorted(base_path.glob(pattern))
                if _is_usable_local_vector_path(path)
            ]
            return matches[0] if matches else None

        if spec.locator_kind == "recursive_glob":
            if not base_path.exists():
                return None
            matches = [
                path
                for pattern in _local_vector_glob_patterns(spec.glob_pattern or "**/*.shp")
                for path in sorted(base_path.glob(pattern))
                if _is_usable_local_vector_path(path)
            ]
            if not matches:
                return None
            if len(matches) == 1:
                return matches[0]
            ranked = self._rank_recursive_matches(matches, aoi=aoi)
            top_score, top_path = ranked[0]
            if top_score > 0 and all(score < top_score for score, _ in ranked[1:]):
                return top_path
            raise ValueError(
                f"Ambiguous raw source match for {source_id}: "
                + ", ".join(str(path) for path in matches[:5])
                + (" ..." if len(matches) > 5 else "")
            )

        return None

    @staticmethod
    def _rank_recursive_matches(matches: list[Path], *, aoi: ResolvedAOI | None) -> list[tuple[int, Path]]:
        if aoi is None:
            return [(0, path) for path in matches]

        exact_hints = [
            _normalize_match_hint(aoi.country_name),
            _normalize_match_hint(aoi.display_name),
            _normalize_match_hint(aoi.query),
        ]
        exact_hints = [hint for hint in exact_hints if hint]

        token_hints = set()
        token_hints.update(_tokenize_match_hint(aoi.country_name))
        token_hints.update(_tokenize_match_hint(aoi.display_name))
        token_hints.update(_tokenize_match_hint(aoi.query))
        if aoi.country_code:
            token_hints.add(str(aoi.country_code).strip().casefold())

        ranked: list[tuple[int, Path]] = []
        for path in matches:
            parts = [_normalize_match_hint(part) for part in path.parts]
            non_empty_parts = [part for part in parts if part]
            path_tokens = {token for part in non_empty_parts for token in part.split()}

            score = 0
            for hint in exact_hints:
                if any(hint == part for part in non_empty_parts):
                    score += 20
            score += sum(1 for token in token_hints if token in path_tokens)
            ranked.append((score, path))

        ranked.sort(key=lambda item: (-item[0], str(item[1])))
        return ranked

    def _resolve_geofabrik_source(
        self,
        source_id: str,
        *,
        request_bbox: Optional[BBox],
        aoi: ResolvedAOI | None,
    ) -> SourceAssetResolution:
        bundle = self._select_geofabrik_bundle(aoi)
        layer_path, asset_cache_hit = self._ensure_geofabrik_layer(source_id, bundle=bundle)
        version_token = _path_version_token(layer_path)

        if request_bbox is None:
            bbox, feature_count = self._inspect_vector_path(layer_path)
            return SourceAssetResolution(
                source_id=source_id,
                path=layer_path,
                source_mode="asset_cached" if asset_cache_hit else "asset_downloaded",
                cache_hit=asset_cache_hit,
                version_token=version_token,
                bbox=bbox,
                feature_count=feature_count,
            )

        target_dir = self.cache_dir / "geofabrik_clips" / bundle.slug / source_id.replace(".", "_") / _bbox_cache_key(request_bbox)
        clipped_path, clip_cache_hit, bbox, feature_count = self._materialize_clipped_vector(
            source_path=layer_path,
            target_dir=target_dir,
            request_bbox=request_bbox,
        )
        return SourceAssetResolution(
            source_id=source_id,
            path=clipped_path,
            source_mode="coverage_empty" if feature_count == 0 else ("asset_cached" if clip_cache_hit else "asset_downloaded"),
            cache_hit=clip_cache_hit,
            version_token=version_token,
            bbox=bbox,
            feature_count=feature_count,
        )

    def _select_geofabrik_bundle(self, aoi: ResolvedAOI | None) -> _GeofabrikBundle:
        if aoi is None or (aoi.country_name is None and aoi.country_code is None):
            return _GeofabrikBundle(slug="burundi", download_url=self.geofabrik_burundi_url)

        country_code = _normalize_country_code(aoi.country_code)
        country_name = _normalize_country_name(aoi.country_name)

        for feature in self._load_geofabrik_index():
            properties = feature.get("properties") or {}
            download_url = str((properties.get("urls") or {}).get("shp") or "").strip()
            if not download_url:
                continue
            iso_codes = properties.get("iso3166-1:alpha2") or []
            if isinstance(iso_codes, str):
                iso_codes = [iso_codes]
            normalized_codes = {_normalize_country_code(code) for code in iso_codes}
            if country_code is not None and country_code in normalized_codes:
                return _GeofabrikBundle(
                    slug=self._geofabrik_slug(properties, download_url),
                    download_url=download_url,
                    boundary_geometry=_feature_geometry(feature),
                )

        for feature in self._load_geofabrik_index():
            properties = feature.get("properties") or {}
            download_url = str((properties.get("urls") or {}).get("shp") or "").strip()
            if not download_url:
                continue
            names = {
                _normalize_country_name(properties.get("name")),
                _normalize_country_name(properties.get("id")),
            }
            if country_name is not None and country_name in names:
                return _GeofabrikBundle(
                    slug=self._geofabrik_slug(properties, download_url),
                    download_url=download_url,
                    boundary_geometry=_feature_geometry(feature),
                )

        raise FileNotFoundError(
            f"No Geofabrik country bundle matched AOI country={aoi.country_name!r} code={aoi.country_code!r}"
        )

    @staticmethod
    def _geofabrik_slug(properties: dict[str, Any], download_url: str) -> str:
        filename = Path(urllib.parse.urlparse(download_url).path).name
        suffix = "-latest-free.shp.zip"
        if filename.endswith(suffix):
            return filename[: -len(suffix)]
        return _slugify(str(properties.get("id") or properties.get("name") or filename).split("/")[-1])

    def _load_geofabrik_index(self) -> list[dict[str, Any]]:
        if self._geofabrik_index_cache is not None:
            return self._geofabrik_index_cache
        payload = json.loads(self._read_text(self.geofabrik_index_url))
        features = payload.get("features") or []
        self._geofabrik_index_cache = [feature for feature in features if isinstance(feature, dict)]
        return self._geofabrik_index_cache

    def _ensure_geofabrik_layer(self, source_id: str, *, bundle: _GeofabrikBundle) -> tuple[Path, bool]:
        asset_dir = self.cache_dir / "geofabrik" / bundle.slug
        filename = Path(urllib.parse.urlparse(bundle.download_url).path).name or f"{bundle.slug}-latest-free.shp.zip"
        zip_path = asset_dir / filename
        extract_dir = asset_dir / "extract"
        marker_path = extract_dir / ".ready"
        layer_path = extract_dir / _GEOFABRIK_LAYER_NAMES[source_id]
        cache_hit = marker_path.exists() and layer_path.exists()
        if cache_hit:
            return layer_path, True

        asset_dir.mkdir(parents=True, exist_ok=True)
        for attempt in range(1, self.http_max_retries + 1):
            if extract_dir.exists():
                shutil.rmtree(extract_dir, ignore_errors=True)
            if not self._is_valid_geofabrik_zip(zip_path):
                try:
                    if zip_path.exists():
                        zip_path.unlink()
                except FileNotFoundError:
                    pass
                self._download_file(bundle.download_url, zip_path)
            try:
                safe_extract_zip(zip_path, extract_dir)
                break
            except zipfile.BadZipFile:
                try:
                    if zip_path.exists():
                        zip_path.unlink()
                except FileNotFoundError:
                    pass
                if attempt >= self.http_max_retries:
                    raise
                time.sleep(min(2 ** (attempt - 1), 3))
        marker_path.write_text("ready\n", encoding="utf-8")
        if not layer_path.exists():
            raise FileNotFoundError(f"Expected Geofabrik layer missing after extraction: {layer_path}")
        return layer_path, False

    @staticmethod
    def _is_valid_geofabrik_zip(zip_path: Path) -> bool:
        if not zip_path.exists():
            return False
        if not zipfile.is_zipfile(zip_path):
            return False
        try:
            with zipfile.ZipFile(zip_path, "r") as archive:
                archive.namelist()
        except zipfile.BadZipFile:
            return False
        return True

    def _resolve_msft_buildings(
        self,
        *,
        request_bbox: Optional[BBox],
        aoi: ResolvedAOI | None,
    ) -> SourceAssetResolution:
        location = (aoi.country_name if aoi is not None else None) or "Burundi"
        location_slug = _slugify(location)
        cache_key = _bbox_cache_key(request_bbox)
        target_dir = self.cache_dir / "msft_buildings" / location_slug / cache_key
        output_shp = target_dir / "microsoft_buildings.shp"
        if _is_usable_local_vector_path(output_shp):
            bbox, feature_count = self._inspect_vector_path(output_shp)
            return SourceAssetResolution(
                source_id="raw.microsoft.building",
                path=output_shp,
                source_mode="coverage_empty" if feature_count == 0 else "asset_cached",
                cache_hit=True,
                version_token=_path_version_token(output_shp),
                bbox=bbox,
                feature_count=feature_count,
            )

        rows = self._load_msft_dataset_rows(location=location)
        if request_bbox is not None:
            rows = [
                row for row in rows if _bbox_intersects(_quadkey_bounds(str(row.get("QuadKey") or "")), request_bbox)
            ]

        frame = self._load_msft_building_frame(rows)
        if request_bbox is not None and not frame.empty:
            frame = clip_frame_to_request_bbox(frame, request_bbox)
        frame = _filter_polygonal_frame(frame)

        target_dir.mkdir(parents=True, exist_ok=True)
        frame.to_file(output_shp)
        bbox = frame_bbox_in_crs(frame)
        feature_count = len(frame.index)
        return SourceAssetResolution(
            source_id="raw.microsoft.building",
            path=output_shp,
            source_mode="coverage_empty" if feature_count == 0 else "asset_downloaded",
            cache_hit=False,
            version_token=_path_version_token(output_shp),
            bbox=bbox,
            feature_count=feature_count,
        )

    def _resolve_google_open_buildings(
        self,
        source_id: str,
        *,
        request_bbox: Optional[BBox],
    ) -> SourceAssetResolution:
        if not self.google_open_buildings_urls:
            raise FileNotFoundError(f"Google Open Buildings URL index is not configured for {source_id}")

        cache_key = _bbox_cache_key(request_bbox)
        urls_key = _url_list_cache_key(self.google_open_buildings_urls)
        target_dir = self.cache_dir / "google_open_buildings" / cache_key / urls_key
        output_gpkg = target_dir / "google_open_buildings.gpkg"
        if _is_usable_local_vector_path(output_gpkg):
            bbox, feature_count = self._inspect_vector_path(output_gpkg)
            return SourceAssetResolution(
                source_id=source_id,
                path=output_gpkg,
                source_mode="coverage_empty" if feature_count == 0 else "asset_cached",
                cache_hit=True,
                version_token=_path_version_token(output_gpkg),
                bbox=bbox,
                feature_count=feature_count,
            )

        frames = [
            self._load_google_open_buildings_frame(
                self._download_cached(url, cache_subdir="google_open_buildings_parts")
            )
            for url in self.google_open_buildings_urls
        ]
        if frames:
            combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs="EPSG:4326")
        else:
            combined = self._empty_google_open_buildings_frame()

        if request_bbox is not None and not combined.empty:
            combined = clip_frame_to_request_bbox(combined, request_bbox)
        combined = _filter_polygonal_frame(combined)

        target_dir.mkdir(parents=True, exist_ok=True)
        combined.to_file(output_gpkg, driver="GPKG")
        bbox = frame_bbox_in_crs(combined)
        feature_count = len(combined.index)
        return SourceAssetResolution(
            source_id=source_id,
            path=output_gpkg,
            source_mode="coverage_empty" if feature_count == 0 else "asset_downloaded",
            cache_hit=False,
            version_token=_path_version_token(output_gpkg),
            bbox=bbox,
            feature_count=feature_count,
        )

    def _load_google_poi_authorization(self) -> dict[str, Any]:
        path = self.google_poi_authorization_path
        if path is None or not path.exists():
            raise PermissionError("Google POI persistence authorization manifest is required.")

        payload = json.loads(path.read_text(encoding="utf-8"))
        authorized_use = payload.get("authorized_use")
        required_use_flags = (
            "persistent_storage",
            "export_vector_files",
            "fuse_with_non_google_sources",
        )
        if (
            payload.get("authorization_status") != "approved"
            or not isinstance(authorized_use, dict)
            or not all(authorized_use.get(flag) is True for flag in required_use_flags)
        ):
            raise PermissionError("Google POI persistence authorization manifest does not allow this use.")
        return payload

    def _resolve_google_poi(self, *, request_bbox: Optional[BBox], aoi: ResolvedAOI | None = None) -> SourceAssetResolution:
        authorization_payload = self._load_google_poi_authorization()
        if self.prefer_local_data:
            local_path = self._try_local_path("raw.google.poi")
            if local_path is None:
                local_path = self._try_spec_local_path("raw.google.poi", aoi=aoi)
            if local_path is not None:
                return self._build_local_resolution(
                    "raw.google.poi",
                    local_path=local_path,
                    request_bbox=request_bbox,
                )

        if not self.google_places_api_key:
            raise PermissionError("GOOGLE_PLACES_API_KEY is required for Google POI acquisition.")
        if self.google_places_fetcher is None or not callable(self.google_places_fetcher):
            raise RuntimeError("A callable google_places_fetcher is required for Google POI acquisition.")

        authorization_path = self.google_poi_authorization_path
        if authorization_path is None:
            raise PermissionError("Google POI persistence authorization manifest is required.")
        authorization_digest = hashlib.sha1(authorization_path.read_bytes()).hexdigest()[:12]
        fetcher_config_digest = self._google_places_fetcher_config_digest()
        target_dir = self.cache_dir / "google_poi" / _bbox_cache_key(request_bbox) / authorization_digest / fetcher_config_digest
        output_gpkg = target_dir / "google_poi.gpkg"
        if _is_usable_local_vector_path(output_gpkg):
            self._write_google_poi_authorization_evidence(target_dir, authorization_payload=authorization_payload)
            bbox, feature_count = self._inspect_vector_path(output_gpkg)
            return SourceAssetResolution(
                source_id="raw.google.poi",
                path=output_gpkg,
                source_mode="coverage_empty" if feature_count == 0 else "asset_cached",
                cache_hit=True,
                version_token=_path_version_token(output_gpkg),
                bbox=bbox,
                feature_count=feature_count,
            )

        rows = list(self.google_places_fetcher(request_bbox, self.google_places_api_key))
        frame = self._google_poi_rows_to_frame(rows)
        if request_bbox is not None and not frame.empty:
            frame = clip_frame_to_request_bbox(frame, request_bbox)

        target_dir.mkdir(parents=True, exist_ok=True)
        frame.to_file(output_gpkg, driver="GPKG")
        self._write_google_poi_authorization_evidence(target_dir, authorization_payload=authorization_payload)

        bbox = frame_bbox_in_crs(frame)
        feature_count = len(frame.index)
        return SourceAssetResolution(
            source_id="raw.google.poi",
            path=output_gpkg,
            source_mode="coverage_empty" if feature_count == 0 else "asset_downloaded",
            cache_hit=False,
            version_token=_path_version_token(output_gpkg),
            bbox=bbox,
            feature_count=feature_count,
        )

    def _google_places_fetcher_config_digest(self) -> str:
        configured_key = self.google_places_cache_key
        if configured_key is None and self.google_places_fetcher is not None:
            configured_key = getattr(self.google_places_fetcher, "cache_key", None)
        if configured_key is None and self.google_places_fetcher is not None:
            version = getattr(self.google_places_fetcher, "version", None)
            configured_key = str(version) if version is not None else None
        payload = str(configured_key or "").strip()
        if not payload:
            raise RuntimeError("A stable non-secret cache key is required for Google POI remote acquisition.")
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]

    def _write_google_poi_authorization_evidence(
        self,
        target_dir: Path,
        *,
        authorization_payload: dict[str, Any],
    ) -> None:
        target_dir.mkdir(parents=True, exist_ok=True)
        manifest_bytes = (
            self.google_poi_authorization_path.read_bytes()
            if self.google_poi_authorization_path is not None and self.google_poi_authorization_path.exists()
            else json.dumps(authorization_payload, sort_keys=True).encode("utf-8")
        )
        evidence = {
            "provider": authorization_payload.get("provider") or "google_places",
            "authorization_status": authorization_payload.get("authorization_status"),
            "authorized_use": {
                key: bool((authorization_payload.get("authorized_use") or {}).get(key))
                for key in (
                    "persistent_storage",
                    "export_vector_files",
                    "fuse_with_non_google_sources",
                )
            },
            "attribution_required": bool(authorization_payload.get("attribution_required", True)),
            "source_manifest_digest": hashlib.sha1(manifest_bytes).hexdigest(),
        }
        (target_dir / "google_poi_authorization_evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _resolve_hydrosheds_water(
        self,
        source_id: str,
        *,
        request_bbox: Optional[BBox],
    ) -> SourceAssetResolution:
        archive_url = (
            self.hydrorivers_global_zip_url
            if source_id == "raw.hydrorivers.water"
            else self.hydrolakes_global_zip_url
        )
        stem_hint = (
            "HydroRIVERS"
            if source_id == "raw.hydrorivers.water"
            else "HydroLAKES"
        )
        asset_dir = self.cache_dir / "hydrosheds" / source_id.replace(".", "_")
        filename = Path(urllib.parse.urlparse(archive_url).path).name or f"{source_id.replace('.', '_')}.zip"
        zip_path = asset_dir / filename
        extract_dir = asset_dir / "extract"
        marker_path = extract_dir / ".ready"

        if not (marker_path.exists() and any(extract_dir.glob("*.shp"))):
            asset_dir.mkdir(parents=True, exist_ok=True)
            if extract_dir.exists():
                shutil.rmtree(extract_dir, ignore_errors=True)
            if not zip_path.exists() or not zipfile.is_zipfile(zip_path):
                self._download_file(archive_url, zip_path)
            safe_extract_zip(zip_path, extract_dir)
            marker_path.write_text("ready\n", encoding="utf-8")

        shp_candidates = sorted(extract_dir.rglob("*.shp"))
        shp_path = next((path for path in shp_candidates if stem_hint.casefold() in path.stem.casefold()), None)
        if shp_path is None and shp_candidates:
            shp_path = shp_candidates[0]
        if shp_path is None:
            raise FileNotFoundError(f"Expected HydroSHEDS shapefile missing after extraction: {extract_dir}")

        version_token = _path_version_token(shp_path)
        if request_bbox is None:
            bbox, feature_count = self._inspect_vector_path(shp_path)
            return SourceAssetResolution(
                source_id=source_id,
                path=shp_path,
                source_mode="asset_cached" if marker_path.exists() else "asset_downloaded",
                cache_hit=marker_path.exists(),
                version_token=version_token,
                bbox=bbox,
                feature_count=feature_count,
            )

        target_dir = self.cache_dir / "hydrosheds_clips" / source_id.replace(".", "_") / _bbox_cache_key(request_bbox)
        clipped_path, clip_cache_hit, bbox, feature_count = self._materialize_clipped_vector(
            source_path=shp_path,
            target_dir=target_dir,
            request_bbox=request_bbox,
        )
        return SourceAssetResolution(
            source_id=source_id,
            path=clipped_path,
            source_mode="coverage_empty" if feature_count == 0 else ("asset_cached" if clip_cache_hit else "asset_downloaded"),
            cache_hit=clip_cache_hit,
            version_token=version_token,
            bbox=bbox,
            feature_count=feature_count,
        )

    def _resolve_gns_poi(
        self,
        *,
        request_bbox: Optional[BBox],
        aoi: ResolvedAOI | None,
    ) -> SourceAssetResolution:
        entry = self._select_gns_country_file(aoi)
        archive_path = self._download_cached(
            entry.download_url,
            cache_subdir=f"gns_country_archives/{_slugify(entry.country_name)}",
        )
        version_token = _path_version_token(archive_path)
        target_dir = (
            self.cache_dir
            / "gns_country_clips"
            / _slugify(entry.country_name)
            / version_token
            / _bbox_cache_key(request_bbox)
        )
        output_gpkg = target_dir / "gns_points.gpkg"
        cache_hit = output_gpkg.exists()
        if not cache_hit:
            frame = self._load_gns_country_frame(archive_path)
            if request_bbox is not None and not frame.empty:
                frame = clip_frame_to_request_bbox(frame, request_bbox)
            target_dir.mkdir(parents=True, exist_ok=True)
            frame.to_file(output_gpkg, driver="GPKG")

        bbox, feature_count = self._inspect_vector_path(output_gpkg)
        return SourceAssetResolution(
            source_id="raw.gns.poi",
            path=output_gpkg,
            source_mode="coverage_empty" if feature_count == 0 else ("asset_cached" if cache_hit else "asset_downloaded"),
            cache_hit=cache_hit,
            version_token=version_token,
            bbox=bbox,
            feature_count=feature_count,
        )

    def _resolve_overture_transportation(
        self,
        *,
        source_id: str = "raw.overture.transportation",
        request_bbox: Optional[BBox],
    ) -> SourceAssetResolution:
        cache_key = _bbox_cache_key(request_bbox)
        asset_dir = self.cache_dir / source_id.replace(".", "_") / cache_key
        raw_path = asset_dir / "segment.geojson"
        filtered_path = asset_dir / "road_segments.geojson"
        marker_path = asset_dir / ".ready"
        cache_hit = marker_path.exists() and filtered_path.exists()

        if not cache_hit:
            asset_dir.mkdir(parents=True, exist_ok=True)
            if not raw_path.exists() or raw_path.stat().st_size == 0:
                if self.overture_transportation_url:
                    self._download_file(self.overture_transportation_url, raw_path)
                else:
                    self._download_overture_transportation_segment(output_path=raw_path, request_bbox=request_bbox)

            try:
                frame = self._load_overture_transportation_frame(raw_path)
            except Exception:
                try:
                    if raw_path.exists():
                        raw_path.unlink()
                except Exception:  # noqa: BLE001
                    pass
                if self.overture_transportation_url:
                    self._download_file(self.overture_transportation_url, raw_path)
                else:
                    self._download_overture_transportation_segment(output_path=raw_path, request_bbox=request_bbox)
                frame = self._load_overture_transportation_frame(raw_path)

            if request_bbox is not None and not frame.empty:
                frame = clip_frame_to_request_bbox(frame, request_bbox)
            frame.to_file(filtered_path, driver="GeoJSON")
            marker_path.write_text("ready\n", encoding="utf-8")

        bbox, feature_count = self._inspect_vector_path(filtered_path)
        return SourceAssetResolution(
            source_id=source_id,
            path=filtered_path,
            source_mode="coverage_empty" if feature_count == 0 else ("asset_cached" if cache_hit else "asset_downloaded"),
            cache_hit=cache_hit,
            version_token=_path_version_token(filtered_path),
            bbox=bbox,
            feature_count=feature_count,
        )

    @staticmethod
    def _load_overture_transportation_frame(raw_path: Path) -> gpd.GeoDataFrame:
        frame = gpd.read_file(raw_path)
        if "subtype" in frame.columns:
            frame = frame[frame["subtype"].fillna("").astype(str).str.casefold() == "road"].copy()
        return frame

    def _select_gns_country_file(self, aoi: ResolvedAOI | None) -> _GNSCountryFile:
        if aoi is None or (not aoi.country_name and not aoi.country_code):
            raise FileNotFoundError("raw.gns.poi remote materialization requires a resolved AOI with country hints")

        requested_name = _normalize_match_hint(aoi.country_name)
        requested_code = str(aoi.country_code or "").strip().upper()
        entries = self._load_gns_download_index()

        if requested_name:
            for entry in entries:
                if _normalize_match_hint(entry.country_name) == requested_name:
                    return entry
            for entry in entries:
                normalized_entry_name = _normalize_match_hint(entry.country_name)
                if requested_name in normalized_entry_name or normalized_entry_name in requested_name:
                    return entry

        if requested_code and len(requested_code) == 3:
            for entry in entries:
                if entry.country_code == requested_code:
                    return entry

        raise FileNotFoundError(
            "No official GNS country download matched the resolved AOI: "
            f"country_name={aoi.country_name!r} country_code={aoi.country_code!r}"
        )

    def _load_gns_download_index(self) -> list[_GNSCountryFile]:
        if self._gns_download_index_cache is not None:
            return self._gns_download_index_cache

        payload = json.loads(self._read_text(self.gns_data_index_url))
        entries: list[_GNSCountryFile] = []
        for row_html in payload.values():
            if not isinstance(row_html, str):
                continue
            href_match = re.search(r"href='([^']+\.(?:zip|7z))'", row_html, flags=re.IGNORECASE)
            code_match = re.search(r"cc='([^']+)'", row_html)
            name_match = re.search(r"cn='([^']+)'", row_html)
            if href_match is None or code_match is None or name_match is None:
                continue
            download_url = unescape(href_match.group(1))
            if "/fc_files/" in download_url or download_url.endswith(".7z"):
                continue
            entries.append(
                _GNSCountryFile(
                    country_code=unescape(code_match.group(1)).strip().upper(),
                    country_name=unescape(name_match.group(1)).strip(),
                    download_url=download_url,
                )
            )
        self._gns_download_index_cache = entries
        return entries

    @staticmethod
    def _load_gns_country_frame(archive_path: Path) -> gpd.GeoDataFrame:
        with zipfile.ZipFile(archive_path, "r") as archive:
            candidates = [
                name
                for name in archive.namelist()
                if name.lower().endswith(".txt")
                and "/" not in name
                and not name.lower().startswith("disclaimer")
                and "guide" not in name.lower()
                and "glossary" not in name.lower()
            ]
            if not candidates:
                raise FileNotFoundError(f"No top-level country text file found in {archive_path}")
            entry_name = sorted(candidates, key=lambda item: len(item))[0]
            with archive.open(entry_name, "r") as handle:
                frame = pd.read_csv(handle, sep="\t", dtype=str, keep_default_na=False)

        frame["lat_dd"] = pd.to_numeric(frame.get("lat_dd"), errors="coerce")
        frame["long_dd"] = pd.to_numeric(frame.get("long_dd"), errors="coerce")
        frame = frame[frame["lat_dd"].notna() & frame["long_dd"].notna()].copy()
        if frame.empty:
            return gpd.GeoDataFrame(frame, geometry=gpd.GeoSeries([], crs="EPSG:4326"), crs="EPSG:4326")
        geometry = gpd.points_from_xy(frame["long_dd"], frame["lat_dd"], crs="EPSG:4326")
        return gpd.GeoDataFrame(frame, geometry=geometry, crs="EPSG:4326")

    def _load_msft_dataset_rows(self, *, location: str) -> list[dict[str, str]]:
        target_name = _normalize_country_name(location)
        text = self._read_text(self.msft_dataset_links_url)
        reader = csv.DictReader(text.splitlines())
        return [
            row
            for row in reader
            if _normalize_country_name(row.get("Location")) == target_name
        ]

    def _load_msft_building_frame(self, rows: Iterable[dict[str, str]]) -> gpd.GeoDataFrame:
        features = list(self._download_msft_features(rows))
        if not features:
            return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs="EPSG:4326")
        return gpd.GeoDataFrame(features, geometry="geometry", crs="EPSG:4326")

    @staticmethod
    def _empty_google_open_buildings_frame() -> gpd.GeoDataFrame:
        return gpd.GeoDataFrame(
            {
                "latitude": pd.Series(dtype="float64"),
                "longitude": pd.Series(dtype="float64"),
                "area_in_meters": pd.Series(dtype="float64"),
                "confidence": pd.Series(dtype="float64"),
            },
            geometry=gpd.GeoSeries([], crs="EPSG:4326"),
            crs="EPSG:4326",
        )

    def _load_google_open_buildings_frame(self, csv_path: Path) -> gpd.GeoDataFrame:
        frame = pd.read_csv(csv_path)
        if "geometry" not in frame.columns:
            raise ValueError(f"Google Open Buildings CSV is missing required geometry WKT column: {csv_path}")
        geometries = frame["geometry"].apply(lambda value: wkt.loads(str(value)) if pd.notna(value) else None)
        frame = frame.drop(columns=["geometry"])
        geo_frame = gpd.GeoDataFrame(frame, geometry=gpd.GeoSeries(geometries, crs="EPSG:4326"), crs="EPSG:4326")
        geo_frame = geo_frame[geo_frame.geometry.notna() & ~geo_frame.geometry.is_empty].copy()
        return _filter_polygonal_frame(geo_frame)

    @staticmethod
    def _google_poi_rows_to_frame(rows: Iterable[dict[str, Any]]) -> gpd.GeoDataFrame:
        base_columns = [
            "place_id",
            "name",
            "name_alt",
            "category",
            "primary_type",
            "type",
            "types",
            "admin_country",
            "country",
            "region_code",
            "lat",
            "lng",
        ]
        normalized_rows = []
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                continue
            location = raw_row.get("location")
            display_name = raw_row.get("displayName")
            lat = raw_row.get("lat", raw_row.get("latitude"))
            lng = raw_row.get("lng", raw_row.get("longitude"))
            if lat is None:
                lat = _nested_mapping_value(location, "latitude")
            if lng is None:
                lng = _nested_mapping_value(location, "longitude")

            display_text = raw_row.get("display_name") or _nested_mapping_value(display_name, "text")
            name_value = raw_row.get("name")
            resource_name = str(name_value).strip() if _is_google_places_resource_name(name_value) else None
            primary_type = raw_row.get("primary_type", raw_row.get("primaryType"))
            types = raw_row.get("types")
            category = raw_row.get("category", primary_type)
            if category is None:
                category = raw_row.get("type")
            if category is None and isinstance(types, list) and types:
                category = types[0]

            normalized_rows.append(
                {
                    "place_id": raw_row.get("place_id") or raw_row.get("id") or resource_name,
                    "name": display_text or (None if resource_name else name_value),
                    "name_alt": (
                        raw_row.get("name_alt")
                        or raw_row.get("formatted_address")
                        or raw_row.get("formattedAddress")
                        or raw_row.get("vicinity")
                        or resource_name
                    ),
                    "category": category,
                    "primary_type": primary_type,
                    "type": raw_row.get("type"),
                    "types": types,
                    "admin_country": raw_row.get("admin_country"),
                    "country": raw_row.get("country"),
                    "region_code": raw_row.get("region_code"),
                    "lat": lat,
                    "lng": lng,
                }
            )

        frame = pd.DataFrame(normalized_rows, columns=base_columns)
        if frame.empty:
            return gpd.GeoDataFrame(
                {column: pd.Series(dtype="object") for column in base_columns},
                geometry=gpd.GeoSeries([], crs="EPSG:4326"),
                crs="EPSG:4326",
            )

        frame["category"] = frame["category"].where(
            frame["category"].notna(),
            frame.get("primary_type", pd.Series(pd.NA, index=frame.index)),
        )
        frame["category"] = frame["category"].where(
            frame["category"].notna(),
            frame.get("type", pd.Series(pd.NA, index=frame.index)),
        )
        frame["lat"] = pd.to_numeric(frame.get("lat"), errors="coerce")
        frame["lng"] = pd.to_numeric(frame.get("lng"), errors="coerce")
        frame = frame[frame["lat"].notna() & frame["lng"].notna()].copy()
        if frame.empty:
            return gpd.GeoDataFrame(
                {column: pd.Series(dtype="object") for column in base_columns},
                geometry=gpd.GeoSeries([], crs="EPSG:4326"),
                crs="EPSG:4326",
            )

        for column in base_columns:
            if column not in frame.columns:
                frame[column] = pd.NA
        frame = frame[base_columns].copy()
        for column in base_columns:
            frame[column] = frame[column].apply(_json_safe_vector_value)
        geometry = gpd.points_from_xy(frame["lng"], frame["lat"], crs="EPSG:4326")
        return gpd.GeoDataFrame(frame, geometry=geometry, crs="EPSG:4326")

    def _download_msft_features(self, rows: Iterable[dict[str, str]]) -> Iterable[dict[str, object]]:
        for row in rows:
            url = str(row.get("Url") or "")
            if not url:
                continue
            last_error: Exception | None = None
            for attempt in range(1, self.http_max_retries + 1):
                gz_path = self._download_cached(
                    url,
                    cache_subdir="msft_parts",
                    force_refresh=attempt > 1,
                )
                try:
                    with gzip.open(gz_path, "rt", encoding="utf-8") as handle:
                        for line in handle:
                            stripped = line.strip()
                            if not stripped:
                                continue
                            feature = json.loads(stripped)
                            geometry = feature.get("geometry")
                            if geometry is None:
                                continue
                            geometry_shape = shape(geometry)
                            if geometry_shape.geom_type not in {"Polygon", "MultiPolygon"}:
                                continue
                            properties = dict(feature.get("properties") or {})
                            properties["geometry"] = geometry_shape
                            yield properties
                    last_error = None
                    break
                except (EOFError, OSError, gzip.BadGzipFile) as exc:
                    last_error = exc
                    try:
                        if gz_path.exists():
                            gz_path.unlink()
                    except Exception:  # noqa: BLE001
                        pass
                    if attempt >= self.http_max_retries:
                        raise
                    time.sleep(min(2 ** (attempt - 1), 3))
            if last_error is not None:
                raise last_error

    def _materialize_clipped_vector(
        self,
        *,
        source_path: Path,
        target_dir: Path,
        request_bbox: BBox,
    ) -> tuple[Path, bool, Optional[BBox], int]:
        output_shp = target_dir / source_path.name
        if _is_usable_local_vector_path(output_shp):
            bbox, feature_count = self._inspect_vector_path(output_shp)
            return output_shp, True, bbox, feature_count

        frame = gpd.read_file(source_path)
        clipped = clip_frame_to_request_bbox(frame, request_bbox)
        target_dir.mkdir(parents=True, exist_ok=True)
        clipped.to_file(output_shp)
        bbox = frame_bbox_in_crs(clipped)
        feature_count = len(clipped.index)
        return output_shp, False, bbox, feature_count

    @staticmethod
    def _inspect_vector_path(path: Path) -> tuple[Optional[BBox], int]:
        frame = gpd.read_file(path)
        return frame_bbox_in_crs(frame), len(frame.index)

    def _download_cached(self, url: str, *, cache_subdir: str, force_refresh: bool = False) -> Path:
        parsed = urllib.parse.urlparse(url)
        filename = Path(parsed.path).name or hashlib.sha1(url.encode("utf-8")).hexdigest()
        url_hash = hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]
        target_dir = self.cache_dir / cache_subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{url_hash}_{filename}"
        if force_refresh and target_path.exists():
            try:
                target_path.unlink()
            except Exception:  # noqa: BLE001
                pass
        if target_path.exists():
            return target_path
        self._download_file(url, target_path)
        return target_path

    def _download_file(self, url: str, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = target_path.with_suffix(target_path.suffix + ".part")
        scheme = urllib.parse.urlparse(url).scheme.lower()
        last_error: Exception | None = None
        for attempt in range(1, self.http_max_retries + 1):
            try:
                if scheme in {"http", "https"}:
                    self._download_http_stream(url, temp_path)
                else:
                    self._download_via_urllib(url, temp_path)
                temp_path.replace(target_path)
                return
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                try:
                    if temp_path.exists():
                        temp_path.unlink()
                except Exception:  # noqa: BLE001
                    pass
                if attempt >= self.http_max_retries:
                    raise
                time.sleep(min(2 ** (attempt - 1), 3))
        if last_error is not None:
            raise last_error

    @staticmethod
    def _resolve_overturemaps_command() -> list[str]:
        overturemaps_bin = shutil.which("overturemaps")
        if overturemaps_bin:
            return [overturemaps_bin]

        uvx_bin = shutil.which("uvx")
        if uvx_bin:
            return [uvx_bin, "overturemaps"]

        raise FileNotFoundError("Neither 'overturemaps' nor 'uvx overturemaps' is available for Overture downloads.")

    def _download_overture_transportation_segment(
        self,
        *,
        output_path: Path,
        request_bbox: Optional[BBox],
    ) -> None:
        command = [
            *self._resolve_overturemaps_command(),
            "download",
            "-f",
            "geojson",
            "--type=segment",
            "-o",
            str(output_path),
        ]
        if request_bbox is not None:
            command.insert(-2, f"--bbox={request_bbox[0]},{request_bbox[1]},{request_bbox[2]},{request_bbox[3]}")
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=OVERTURE_DOWNLOAD_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "Overture transportation download timed out: "
                f"timeout={OVERTURE_DOWNLOAD_TIMEOUT_SECONDS}s command={' '.join(command)}"
            ) from exc
        if completed.returncode != 0:
            raise RuntimeError(
                "Overture transportation download failed: "
                f"exit={completed.returncode} stderr={completed.stderr.strip() or completed.stdout.strip()}"
            )
        if not output_path.exists():
            raise FileNotFoundError(f"Overture transportation download completed without output file: {output_path}")

    def _download_http_stream(self, url: str, target_path: Path) -> None:
        try:
            with httpx.stream("GET", url, timeout=120.0, follow_redirects=True) as response:
                response.raise_for_status()
                with target_path.open("wb") as handle:
                    for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                        if chunk:
                            handle.write(chunk)
            return
        except Exception:
            pass

        try:
            self._download_http_via_curl(url, target_path)
            return
        except Exception:
            pass

        self._download_via_urllib(url, target_path)

    @staticmethod
    def _download_via_urllib(url: str, target_path: Path) -> None:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=120) as response, target_path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)

    @staticmethod
    def _download_http_via_curl(url: str, target_path: Path) -> None:
        curl_bin = shutil.which("curl.exe") or shutil.which("curl")
        if not curl_bin:
            raise RuntimeError("curl binary is not available for HTTPS download fallback")
        completed = subprocess.run(
            [curl_bin, "-L", "--fail", "--output", str(target_path), url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            text=True,
        )
        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            stdout = (completed.stdout or "").strip()
            message = stderr or stdout or f"curl exited with code {completed.returncode}"
            raise RuntimeError(message)

    def _read_text(self, url: str) -> str:
        return self._read_binary(url).decode("utf-8")

    def _read_binary(self, url: str) -> bytes:
        request = urllib.request.Request(url, method="GET")
        last_error: Exception | None = None
        for attempt in range(1, self.http_max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=120) as response:
                    return response.read()
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= self.http_max_retries:
                    raise
                time.sleep(min(2 ** (attempt - 1), 3))
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Failed to read URL with unknown error: {url}")
