from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import geopandas as gpd
from shapely.geometry import shape

from services.aoi_resolution_service import ResolvedAOI
from utils.shp_zip import collect_bundle_files, safe_extract_zip
from utils.vector_clip import BBox, clip_frame_to_request_bbox, frame_bbox_in_crs


GEOFABRIK_BURUNDI_SHP_URL = "https://download.geofabrik.de/africa/burundi-latest-free.shp.zip"
GEOFABRIK_INDEX_URL = "https://download.geofabrik.de/index-v1.json"
MSFT_BUILDING_DATASET_LINKS_URL = "https://minedbuildings.z5.web.core.windows.net/global-buildings/dataset-links.csv"


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
    "raw.osm.water": [
        ("Data", "water"),
        ("Data", "burundi-260127-free.shp", "gis_osm_water_a_free_1.shp"),
    ],
    "raw.osm.poi": [
        ("Data", "POI"),
        ("Data", "burundi-260127-free.shp", "gis_osm_pois_free_1.shp"),
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
}


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
        prefer_local_data: bool = True,
        http_max_retries: int = 3,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.geofabrik_burundi_url = geofabrik_burundi_url
        self.geofabrik_index_url = geofabrik_index_url
        self.msft_dataset_links_url = msft_dataset_links_url
        self.prefer_local_data = prefer_local_data
        self.http_max_retries = max(1, int(http_max_retries))
        self._geofabrik_index_cache: list[dict[str, Any]] | None = None

    def can_materialize(self, source_id: str) -> bool:
        return source_id in _REMOTELY_MATERIALIZABLE_SOURCE_IDS or source_id in _LOCAL_SOURCE_CANDIDATES

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
        if not zip_path.exists():
            self._download_file(bundle.download_url, zip_path)
        safe_extract_zip(zip_path, extract_dir)
        marker_path.write_text("ready\n", encoding="utf-8")
        if not layer_path.exists():
            raise FileNotFoundError(f"Expected Geofabrik layer missing after extraction: {layer_path}")
        return layer_path, False

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
        request = urllib.request.Request(url, method="GET")
        temp_path = target_path.with_suffix(target_path.suffix + ".part")
        last_error: Exception | None = None
        for attempt in range(1, self.http_max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=120) as response, temp_path.open("wb") as handle:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
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
