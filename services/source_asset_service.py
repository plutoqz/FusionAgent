from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import geopandas as gpd
from shapely.geometry import shape

from utils.shp_zip import collect_bundle_files, safe_extract_zip
from utils.vector_clip import BBox, clip_frame_to_request_bbox


GEOFABRIK_BURUNDI_SHP_URL = "https://download.geofabrik.de/africa/burundi-latest-free.shp.zip"
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


class SourceAssetService:
    def __init__(
        self,
        *,
        repo_root: Path,
        cache_dir: Path,
        geofabrik_burundi_url: str = GEOFABRIK_BURUNDI_SHP_URL,
        msft_dataset_links_url: str = MSFT_BUILDING_DATASET_LINKS_URL,
        prefer_local_data: bool = True,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.geofabrik_burundi_url = geofabrik_burundi_url
        self.msft_dataset_links_url = msft_dataset_links_url
        self.prefer_local_data = prefer_local_data

    def can_materialize(self, source_id: str) -> bool:
        return source_id in _REMOTELY_MATERIALIZABLE_SOURCE_IDS or source_id in _LOCAL_SOURCE_CANDIDATES

    def resolve_raw_source_path(
        self,
        source_id: str,
        *,
        request_bbox: Optional[BBox] = None,
    ) -> SourceAssetResolution:
        if self.prefer_local_data:
            local_path = self._try_local_path(source_id)
            if local_path is not None:
                return SourceAssetResolution(
                    source_id=source_id,
                    path=local_path,
                    source_mode="local_data",
                    cache_hit=True,
                    version_token=_path_version_token(local_path),
                )

        if source_id in _GEOFABRIK_LAYER_NAMES:
            layer_path, cache_hit = self._ensure_geofabrik_layer(source_id)
            return SourceAssetResolution(
                source_id=source_id,
                path=layer_path,
                source_mode="asset_cached" if cache_hit else "asset_downloaded",
                cache_hit=cache_hit,
                version_token=_path_version_token(layer_path),
            )

        if source_id == "raw.microsoft.building":
            clipped_path, cache_hit = self._ensure_msft_building_layer(request_bbox=request_bbox)
            return SourceAssetResolution(
                source_id=source_id,
                path=clipped_path,
                source_mode="asset_cached" if cache_hit else "asset_downloaded",
                cache_hit=cache_hit,
                version_token=_path_version_token(clipped_path),
            )

        raise FileNotFoundError(f"No local or remote source asset path available for {source_id}")

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

    def _ensure_geofabrik_layer(self, source_id: str) -> tuple[Path, bool]:
        asset_dir = self.cache_dir / "geofabrik_burundi"
        zip_path = asset_dir / "burundi-latest-free.shp.zip"
        extract_dir = asset_dir / "extract"
        marker_path = extract_dir / ".ready"
        layer_path = extract_dir / _GEOFABRIK_LAYER_NAMES[source_id]
        cache_hit = marker_path.exists() and layer_path.exists()
        if cache_hit:
            return layer_path, True

        asset_dir.mkdir(parents=True, exist_ok=True)
        if not zip_path.exists():
            self._download_file(self.geofabrik_burundi_url, zip_path)
        if extract_dir.exists():
            for item in extract_dir.iterdir():
                if item.is_dir():
                    for child in item.rglob("*"):
                        pass
            # Leave existing files in place; safe_extract_zip will overwrite as needed.
        safe_extract_zip(zip_path, extract_dir)
        marker_path.write_text("ready\n", encoding="utf-8")
        if not layer_path.exists():
            raise FileNotFoundError(f"Expected Geofabrik layer missing after extraction: {layer_path}")
        return layer_path, False

    def _ensure_msft_building_layer(self, *, request_bbox: Optional[BBox]) -> tuple[Path, bool]:
        cache_key = "full" if request_bbox is None else hashlib.sha1(repr(tuple(request_bbox)).encode("utf-8")).hexdigest()[:12]
        target_dir = self.cache_dir / "msft_burundi_buildings" / cache_key
        output_shp = target_dir / "microsoft_buildings.shp"
        if output_shp.exists():
            return output_shp, True

        rows = self._load_msft_dataset_rows(location="Burundi")
        if request_bbox is not None:
            filtered_rows = [
                row for row in rows if _bbox_intersects(_quadkey_bounds(str(row["QuadKey"])), request_bbox)
            ]
            rows = filtered_rows or rows

        features = list(self._download_msft_features(rows))
        if not features:
            raise FileNotFoundError("No Microsoft building features were available for the requested source.")

        frame = gpd.GeoDataFrame(features, geometry="geometry", crs="EPSG:4326")
        if request_bbox is not None:
            frame = clip_frame_to_request_bbox(frame, request_bbox)
        if frame.empty:
            raise ValueError("Microsoft building source materialization produced no features for the requested bbox.")

        target_dir.mkdir(parents=True, exist_ok=True)
        frame.to_file(output_shp)
        return output_shp, False

    def _load_msft_dataset_rows(self, *, location: str) -> list[dict[str, str]]:
        text = self._read_text(self.msft_dataset_links_url)
        reader = csv.DictReader(text.splitlines())
        return [row for row in reader if str(row.get("Location") or "") == location]

    def _download_msft_features(self, rows: Iterable[dict[str, str]]) -> Iterable[dict[str, object]]:
        for row in rows:
            url = str(row.get("Url") or "")
            if not url:
                continue
            gz_path = self._download_cached(url, cache_subdir="msft_parts")
            with gzip.open(gz_path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    feature = json.loads(stripped)
                    geometry = feature.get("geometry")
                    if geometry is None:
                        continue
                    properties = dict(feature.get("properties") or {})
                    properties["geometry"] = shape(geometry)
                    yield properties

    def _download_cached(self, url: str, *, cache_subdir: str) -> Path:
        parsed = urllib.parse.urlparse(url)
        filename = Path(parsed.path).name or hashlib.sha1(url.encode("utf-8")).hexdigest()
        target_dir = self.cache_dir / cache_subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / filename
        if target_path.exists():
            return target_path
        self._download_file(url, target_path)
        return target_path

    @staticmethod
    def _download_file(url: str, target_path: Path) -> None:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=120) as response, target_path.open("wb") as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)

    @staticmethod
    def _read_text(url: str) -> str:
        request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = response.read()
        return payload.decode("utf-8")
