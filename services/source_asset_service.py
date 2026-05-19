from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import geopandas as gpd
import httpx
from shapely.geometry import shape

from kg.source_catalog import get_raw_vector_source_spec
from services.aoi_resolution_service import ResolvedAOI
from utils.raster_cli import gdalinfo_json
from utils.shp_zip import collect_bundle_files, safe_extract_zip
from utils.vector_clip import BBox, clip_frame_to_request_bbox, frame_bbox_in_crs


GEOFABRIK_BURUNDI_SHP_URL = "https://download.geofabrik.de/africa/burundi-latest-free.shp.zip"
GEOFABRIK_INDEX_URL = "https://download.geofabrik.de/index-v1.json"
MSFT_BUILDING_DATASET_LINKS_URL = "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv"
HYDRORIVERS_GLOBAL_ZIP_URL = "https://data.hydrosheds.org/file/HydroRIVERS/HydroRIVERS_v10_shp.zip"
HYDROLAKES_GLOBAL_ZIP_URL = "https://data.hydrosheds.org/file/hydrolakes/HydroLAKES_polys_v10_shp.zip"
OVERTURE_DOWNLOAD_TIMEOUT_SECONDS = 15


_GEOFABRIK_LAYER_NAMES = {
    "raw.osm.building": "gis_osm_buildings_a_free_1.shp",
    "raw.osm.road": "gis_osm_roads_free_1.shp",
    "raw.osm.water": "gis_osm_water_a_free_1.shp",
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
    "raw.osm.poi",
    "raw.microsoft.building",
    "raw.overture.transportation",
    "raw.overture.road",
    "raw.hydrorivers.water",
    "raw.hydrolakes.water",
}
# raw.google.building is intentionally absent: it remains a local/manual-only
# source until an official, tested remote materialization path exists.


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
    if "no local or remote source asset path available" in text or "not found" in text or "missing" in text:
        return "SOURCE_MISSING"
    if source.get("path") in {None, ""}:
        return "SOURCE_MISSING"
    return "SOURCE_CORRUPTED"


@dataclass(frozen=True)
class _GeofabrikBundle:
    slug: str
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


def _bbox_cache_key(request_bbox: Optional[BBox]) -> str:
    if request_bbox is None:
        return "full"
    return hashlib.sha1(repr(tuple(request_bbox)).encode("utf-8")).hexdigest()[:12]


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
        overture_transportation_url: str | None = None,
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
        self.overture_transportation_url = overture_transportation_url
        self.hydrorivers_global_zip_url = hydrorivers_global_zip_url
        self.hydrolakes_global_zip_url = hydrolakes_global_zip_url
        self.prefer_local_data = prefer_local_data
        self.http_max_retries = max(1, int(http_max_retries))
        self._geofabrik_index_cache: list[dict[str, Any]] | None = None

    def can_materialize(self, source_id: str) -> bool:
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
        effective_bbox = request_bbox or (tuple(aoi.bbox) if aoi is not None else None)

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
        if source_id in {"raw.overture.transportation", "raw.overture.road"}:
            return self._resolve_overture_transportation(source_id=source_id, request_bbox=effective_bbox)
        if source_id in {"raw.hydrorivers.water", "raw.hydrolakes.water"}:
            return self._resolve_hydrosheds_water(source_id, request_bbox=effective_bbox)

        raise FileNotFoundError(f"No local or remote source asset path available for {source_id}")

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
                matches = sorted(candidate.glob("*.shp"))
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
            matches = [path for path in sorted(base_path.glob("*.shp")) if _is_usable_local_vector_path(path)]
            return matches[0] if matches else None

        if spec.locator_kind == "recursive_glob":
            if not base_path.exists():
                return None
            matches = [path for path in sorted(base_path.glob(spec.glob_pattern or "**/*.shp")) if _is_usable_local_vector_path(path)]
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
                return _GeofabrikBundle(slug=self._geofabrik_slug(properties, download_url), download_url=download_url)

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
                return _GeofabrikBundle(slug=self._geofabrik_slug(properties, download_url), download_url=download_url)

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
            if self.overture_transportation_url:
                self._download_file(self.overture_transportation_url, raw_path)
            else:
                self._download_overture_transportation_segment(output_path=raw_path, request_bbox=request_bbox)

            frame = gpd.read_file(raw_path)
            if "subtype" in frame.columns:
                frame = frame[frame["subtype"].fillna("").astype(str).str.casefold() == "road"].copy()
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
        target_dir = self.cache_dir / cache_subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / filename
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
