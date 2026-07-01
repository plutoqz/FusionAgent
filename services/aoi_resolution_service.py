from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol

import geopandas as gpd
from shapely.geometry import box
from shapely.ops import unary_union

from services.scenario_trigger_normalizer import normalize_scenario_trigger_text
from utils.vector_clip import REQUEST_BBOX_CRS, filter_frame_to_intersecting_geometry, frame_bbox_in_crs


_DISASTER_PREFIX_RE = re.compile(
    r"^\s*(earthquake|flood|typhoon|disaster|emergency)\s+(in|at|near|around)\s+",
    flags=re.IGNORECASE,
)

_DISASTER_SUFFIX_RE = re.compile(
    r"\s+(after|following|during|because of|due to)\s+(an?\s+)?"
    r"(earthquake|flood|typhoon|disaster|emergency)\b.*$",
    flags=re.IGNORECASE,
)

_NEED_SUFFIX_RE = re.compile(
    r"\s*,?\s*(need|needs|requiring|requires)\s+"
    r"(building|road|water|poi|data|fusion).*$",
    flags=re.IGNORECASE,
)


def _clean_location_phrase(value: str) -> str:
    cleaned = _DISASTER_PREFIX_RE.sub("", value).strip(" .,:;")
    cleaned = _DISASTER_SUFFIX_RE.sub("", cleaned).strip(" .,:;")
    cleaned = _NEED_SUFFIX_RE.sub("", cleaned).strip(" .,:;")
    return cleaned


class Geocoder(Protocol):
    def search(self, query: str) -> Iterable[dict[str, Any]]: ...


class NominatimGeocoder:
    def __init__(
        self,
        *,
        base_url: str = "https://nominatim.openstreetmap.org/search",
        user_agent: str = "GeoFusion/1.0 (+https://openai.com/codex)",
        limit: int = 5,
        timeout_seconds: int = 30,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url
        self.user_agent = user_agent
        self.limit = max(1, int(limit))
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.max_retries = max(1, int(max_retries))

    def search(self, query: str) -> Iterable[dict[str, Any]]:
        params = urllib.parse.urlencode(
            {
                "q": query,
                "format": "jsonv2",
                "limit": self.limit,
                "addressdetails": 1,
            }
        )
        url = f"{self.base_url}?{params}"
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": self.user_agent,
                "Accept": "application/json",
            },
            method="GET",
        )
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    return list(json.loads(response.read().decode("utf-8")))
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                if attempt >= self.max_retries:
                    raise
                time.sleep(min(2 ** (attempt - 1), 3))
        if last_error is not None:
            raise last_error
        return []


@dataclass(frozen=True)
class ResolvedAOICandidate:
    query: str
    display_name: str
    country_name: str | None
    country_code: str | None
    admin_level: str | None
    bbox: tuple[float, float, float, float]
    source: str
    confidence: float
    raw: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ResolvedAOI:
    query: str
    display_name: str
    country_name: str | None
    country_code: str | None
    bbox: tuple[float, float, float, float]
    confidence: float
    selection_reason: str
    candidates: tuple[ResolvedAOICandidate, ...]
    admin_level: str | None = None
    boundary_source_id: str | None = None
    boundary_artifact_path: str | None = None
    clip_geometry_hash: str | None = None
    degraded_bbox_clip: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        payload["clip_geometry_hash"] = self.clip_geometry_hash or _bbox_geometry_hash(self.bbox)
        return payload


class AOIAmbiguityError(ValueError):
    def __init__(self, query: str, candidates: tuple[ResolvedAOICandidate, ...]) -> None:
        self.query = query
        self.candidates = candidates
        super().__init__(f"Ambiguous AOI query: {query}")


class AOIResolutionService:
    """Resolve task text to an AOI through an injected geocoder.

    Runtime callers normally pass NominatimGeocoder. Tests and maturity checks
    should inject a deterministic fake Geocoder so AOI selection evidence is
    reproducible without hiding the external geocoder dependency.
    """

    def __init__(
        self,
        *,
        geocoder: Geocoder,
        admin_boundary_resolver: "AdminBoundaryResolver | None" = None,
    ) -> None:
        self.geocoder = geocoder
        self.admin_boundary_resolver = admin_boundary_resolver

    def resolve(self, user_query: str) -> ResolvedAOI:
        location_query = self.extract_location_query(user_query)
        raw_candidates = list(self.geocoder.search(location_query))
        if not raw_candidates:
            raise ValueError(f"AOI_RESOLUTION_FAILED: No AOI candidates found for query: {location_query}")

        candidates = tuple(self._deduplicate_candidates(self._normalize_candidate(location_query, raw) for raw in raw_candidates))
        resolved = self._select_candidate(location_query, candidates)
        if self.admin_boundary_resolver is None:
            return resolved
        boundary = self.admin_boundary_resolver.resolve(resolved)
        if boundary is None:
            return resolved
        return _resolved_aoi_with_boundary(resolved, boundary)

    @staticmethod
    def extract_location_query(user_query: str) -> str:
        query = (user_query or "").strip()
        if not query:
            raise ValueError("AOI query must not be empty.")

        normalized = normalize_scenario_trigger_text(query)
        if normalized.normalized_location:
            return normalized.normalized_location

        patterns = [
            r"\bfor\s+(?P<location>.+)$",
            r"\bin\s+(?P<location>.+)$",
            r"\baround\s+(?P<location>.+)$",
            r"\bwithin\s+(?P<location>.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, query, flags=re.IGNORECASE)
            if match:
                location = _clean_location_phrase(match.group("location"))
                if location:
                    return location
        return _clean_location_phrase(query)

    @staticmethod
    def _normalize_candidate(query: str, raw: dict[str, Any]) -> ResolvedAOICandidate:
        display_name = str(raw.get("display_name") or raw.get("name") or query).strip()
        address = raw.get("address") or {}
        country_name = _as_optional_text(address.get("country") or raw.get("country"))
        country_code = _as_optional_text(address.get("country_code") or raw.get("country_code"))
        if country_code is not None:
            country_code = country_code.lower()

        bbox = _extract_bbox(raw)
        admin_level = _derive_admin_level(address, raw)
        confidence = _as_float(raw.get("confidence"), default=None)
        if confidence is None:
            confidence = _as_float(raw.get("importance"), default=0.0)

        return ResolvedAOICandidate(
            query=query,
            display_name=display_name,
            country_name=country_name,
            country_code=country_code,
            admin_level=admin_level,
            bbox=bbox,
            source=str(raw.get("source") or "geocoder"),
            confidence=confidence,
            raw=dict(raw),
        )

    @staticmethod
    def _deduplicate_candidates(candidates: Iterable[ResolvedAOICandidate]) -> tuple[ResolvedAOICandidate, ...]:
        deduped: dict[tuple[str, str | None, tuple[float, float, float, float]], ResolvedAOICandidate] = {}
        for candidate in candidates:
            key = (
                candidate.display_name.strip().casefold(),
                candidate.country_code,
                tuple(round(value, 7) for value in candidate.bbox),
            )
            existing = deduped.get(key)
            if existing is None or candidate.confidence > existing.confidence:
                deduped[key] = candidate
        return tuple(deduped.values())

    @staticmethod
    def _select_candidate(query: str, candidates: tuple[ResolvedAOICandidate, ...]) -> ResolvedAOI:
        if not candidates:
            raise ValueError(f"No AOI candidates found for query: {query}")
        ordered = tuple(sorted(candidates, key=lambda item: item.confidence, reverse=True))
        if len(ordered) == 1:
            chosen = ordered[0]
            return ResolvedAOI(
                query=query,
                display_name=chosen.display_name,
                country_name=chosen.country_name,
                country_code=chosen.country_code,
                bbox=chosen.bbox,
                confidence=chosen.confidence,
                selection_reason="single_candidate",
                candidates=ordered,
                admin_level=chosen.admin_level,
                boundary_source_id="bbox_fallback",
                clip_geometry_hash=_bbox_geometry_hash(chosen.bbox),
                degraded_bbox_clip=True,
            )

        top, second = ordered[0], ordered[1]
        if top.confidence - second.confidence >= 0.10:
            return ResolvedAOI(
                query=query,
                display_name=top.display_name,
                country_name=top.country_name,
                country_code=top.country_code,
                bbox=top.bbox,
                confidence=top.confidence,
                selection_reason="top_confidence_margin",
                candidates=ordered,
                admin_level=top.admin_level,
                boundary_source_id="bbox_fallback",
                clip_geometry_hash=_bbox_geometry_hash(top.bbox),
                degraded_bbox_clip=True,
            )

        nested_specific = AOIResolutionService._select_nested_specific_candidate(ordered)
        if nested_specific is not None:
            return ResolvedAOI(
                query=query,
                display_name=nested_specific.display_name,
                country_name=nested_specific.country_name,
                country_code=nested_specific.country_code,
                bbox=nested_specific.bbox,
                confidence=nested_specific.confidence,
                selection_reason="nested_specificity_preference",
                candidates=ordered,
                admin_level=nested_specific.admin_level,
                boundary_source_id="bbox_fallback",
                clip_geometry_hash=_bbox_geometry_hash(nested_specific.bbox),
                degraded_bbox_clip=True,
            )

        raise AOIAmbiguityError(query, ordered)

    @staticmethod
    def _select_nested_specific_candidate(
        candidates: tuple[ResolvedAOICandidate, ...],
    ) -> ResolvedAOICandidate | None:
        if len(candidates) < 2:
            return None
        for candidate in candidates:
            if candidate.admin_level != "city":
                continue
            for other in candidates:
                if other is candidate:
                    continue
                if candidate.country_code != other.country_code:
                    continue
                if candidate.display_name.strip().casefold() != other.display_name.strip().casefold():
                    continue
                if _bbox_contains(other.bbox, candidate.bbox) and candidate.bbox != other.bbox:
                    return candidate
        return None


@dataclass(frozen=True)
class AdminBoundaryResolution:
    source_id: str
    artifact_path: Path
    geometry_hash: str

    def to_resolved_aoi_update(self) -> dict[str, Any]:
        return {
            "boundary_source_id": self.source_id,
            "boundary_artifact_path": str(self.artifact_path),
            "clip_geometry_hash": self.geometry_hash,
            "degraded_bbox_clip": False,
        }


class AdminBoundaryResolver:
    """Resolve local administrative boundary polygons for AOI clipping.

    The resolver is intentionally local-first. Operators can provide a boundary
    directory/file through GEOFUSION_ADMIN_BOUNDARY_PATH; otherwise it scans
    common preload locations under the repository root.
    """

    def __init__(
        self,
        *,
        repo_root: Path,
        cache_dir: Path,
        search_paths: Iterable[Path] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.cache_dir = Path(cache_dir)
        self.search_paths = tuple(search_paths) if search_paths is not None else self._default_search_paths()

    def resolve(self, aoi: ResolvedAOI) -> AdminBoundaryResolution | None:
        matches = self._candidate_paths()
        if not matches:
            return None
        ranked = self._rank_candidate_paths(matches, aoi=aoi)
        for source_id, path in ranked:
            boundary = _boundary_frame_for_aoi(path, aoi)
            if boundary is None or boundary.empty:
                continue
            artifact_path = self._write_boundary_artifact(boundary, aoi=aoi, source_id=source_id, source_path=path)
            geometry_hash = _frame_geometry_hash(boundary)
            return AdminBoundaryResolution(
                source_id=source_id,
                artifact_path=artifact_path,
                geometry_hash=geometry_hash,
            )
        return None

    def _default_search_paths(self) -> tuple[Path, ...]:
        configured = os.getenv("GEOFUSION_ADMIN_BOUNDARY_PATH")
        paths: list[Path] = []
        if configured:
            paths.extend(Path(item.strip()) for item in configured.split(os.pathsep) if item.strip())
        paths.extend(
            [
                self.repo_root / "Data" / "admin" / "OSM",
                self.repo_root / "Data" / "admin" / "GeoBoundaries",
                self.repo_root / "Data" / "admin",
                self.repo_root / "data" / "admin" / "OSM",
                self.repo_root / "data" / "admin" / "GeoBoundaries",
                self.repo_root / "data" / "admin",
            ]
        )
        return tuple(paths)

    def _candidate_paths(self) -> list[tuple[str, Path]]:
        candidates: list[tuple[str, Path]] = []
        for raw_path in self.search_paths:
            path = raw_path if raw_path.is_absolute() else self.repo_root / raw_path
            if not path.exists():
                continue
            source_id = _admin_boundary_source_id(path)
            if path.is_file() and path.suffix.lower() in {".shp", ".gpkg", ".geojson", ".json"}:
                candidates.append((source_id, path))
                continue
            if path.is_dir():
                for pattern in ("*.gpkg", "*.shp", "*.geojson", "*.json", "**/*.gpkg", "**/*.shp", "**/*.geojson", "**/*.json"):
                    for match in sorted(path.glob(pattern)):
                        if match.is_file():
                            candidates.append((_admin_boundary_source_id(match), match))
        seen: set[Path] = set()
        unique: list[tuple[str, Path]] = []
        for source_id, path in candidates:
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append((source_id, path))
        return unique

    def _rank_candidate_paths(self, matches: list[tuple[str, Path]], *, aoi: ResolvedAOI) -> list[tuple[str, Path]]:
        hints = _boundary_match_hints(aoi)
        ranked: list[tuple[int, str, Path]] = []
        for source_id, path in matches:
            path_text = _normalize_boundary_hint(" ".join(path.parts))
            score = 0
            for hint in hints:
                if hint and hint in path_text:
                    score += 10 + len(hint.split())
            ranked.append((score, source_id, path))
        ranked.sort(key=lambda item: (-item[0], str(item[2])))
        return [(source_id, path) for _, source_id, path in ranked]

    def _write_boundary_artifact(
        self,
        boundary: gpd.GeoDataFrame,
        *,
        aoi: ResolvedAOI,
        source_id: str,
        source_path: Path,
    ) -> Path:
        geometry_hash = _frame_geometry_hash(boundary)
        artifact_dir = self.cache_dir / "admin_boundaries" / source_id.replace(".", "_") / geometry_hash[:16]
        artifact_path = artifact_dir / "boundary.gpkg"
        if artifact_path.exists():
            return artifact_path
        artifact_dir.mkdir(parents=True, exist_ok=True)
        out = boundary.copy()
        out["boundary_source_id"] = source_id
        out["boundary_source_path"] = str(source_path)
        out["aoi_query"] = aoi.query
        out["aoi_display_name"] = aoi.display_name
        out.to_file(artifact_path, driver="GPKG")
        return artifact_path


def _extract_bbox(raw: dict[str, Any]) -> tuple[float, float, float, float]:
    bbox = raw.get("boundingbox")
    if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        south, north, west, east = (float(value) for value in bbox)
        return (west, south, east, north)

    lat = _as_float(raw.get("lat"), default=None)
    lon = _as_float(raw.get("lon"), default=None)
    if lat is None or lon is None:
        raise ValueError(f"AOI candidate is missing boundingbox and lat/lon: {raw}")
    return (lon, lat, lon, lat)


def _derive_admin_level(address: dict[str, Any], raw: dict[str, Any]) -> str | None:
    for key, value in (
        ("city", address.get("city")),
        ("county", address.get("county")),
        ("state", address.get("state")),
        ("country", address.get("country")),
    ):
        if value:
            return key
    return _as_optional_text(raw.get("type") or raw.get("class"))


def _as_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_float(value: Any, default: float | None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except Exception:  # noqa: BLE001
        return default


def _bbox_contains(outer: tuple[float, float, float, float], inner: tuple[float, float, float, float]) -> bool:
    return (
        outer[0] <= inner[0]
        and outer[1] <= inner[1]
        and outer[2] >= inner[2]
        and outer[3] >= inner[3]
    )


def _bbox_geometry_hash(bbox: tuple[float, float, float, float]) -> str:
    normalized = ",".join(f"{float(value):.7f}" for value in bbox)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _resolved_aoi_with_boundary(resolved: ResolvedAOI, boundary: AdminBoundaryResolution) -> ResolvedAOI:
    return ResolvedAOI(
        query=resolved.query,
        display_name=resolved.display_name,
        country_name=resolved.country_name,
        country_code=resolved.country_code,
        bbox=resolved.bbox,
        confidence=resolved.confidence,
        selection_reason=resolved.selection_reason,
        candidates=resolved.candidates,
        admin_level=resolved.admin_level,
        **boundary.to_resolved_aoi_update(),
    )


def _admin_boundary_source_id(path: Path) -> str:
    text = " ".join(path.parts).casefold()
    if "geobound" in text:
        return "raw.geoboundaries.admin"
    return "raw.osm.admin_boundary"


def _boundary_match_hints(aoi: ResolvedAOI) -> list[str]:
    raw_hints = [
        aoi.query,
        aoi.display_name,
        aoi.country_name,
        aoi.country_code,
        *(str(aoi.display_name or "").split(",")),
    ]
    return [_normalize_boundary_hint(item) for item in raw_hints if _normalize_boundary_hint(item)]


def _normalize_boundary_hint(value: Any) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"[^0-9a-z]+", " ", text)
    return " ".join(part for part in text.split() if part)


def _boundary_frame_for_aoi(path: Path, aoi: ResolvedAOI) -> gpd.GeoDataFrame | None:
    frame = gpd.read_file(path)
    if frame.empty:
        return None
    frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
    if frame.empty:
        return None
    if frame.crs is None:
        frame = frame.set_crs(REQUEST_BBOX_CRS)

    scored = _score_boundary_rows(frame, aoi)
    if scored is not None and not scored.empty:
        frame = scored

    bbox_mask = box(*aoi.bbox)
    if frame.crs is not None and str(frame.crs) != REQUEST_BBOX_CRS:
        mask_frame = gpd.GeoDataFrame(geometry=[bbox_mask], crs=REQUEST_BBOX_CRS).to_crs(frame.crs)
        bbox_mask = mask_frame.geometry.iloc[0]
    intersecting = filter_frame_to_intersecting_geometry(frame, bbox_mask)
    if intersecting.empty:
        return None
    polygons = intersecting[intersecting.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    if polygons.empty:
        return None
    unioned = unary_union([geometry for geometry in polygons.geometry if geometry is not None and not geometry.is_empty])
    if unioned is None or unioned.is_empty:
        return None
    return gpd.GeoDataFrame({"name": [aoi.display_name]}, geometry=[unioned], crs=polygons.crs).to_crs(REQUEST_BBOX_CRS)


def _score_boundary_rows(frame: gpd.GeoDataFrame, aoi: ResolvedAOI) -> gpd.GeoDataFrame | None:
    hints = _boundary_match_hints(aoi)
    if not hints:
        return None
    text_columns = [
        column
        for column in frame.columns
        if column != frame.geometry.name and frame[column].dtype == object
    ]
    if not text_columns:
        return None
    scores: list[int] = []
    for _, row in frame.iterrows():
        row_text = _normalize_boundary_hint(" ".join(str(row.get(column) or "") for column in text_columns))
        score = sum(1 for hint in hints if hint and hint in row_text)
        scores.append(score)
    max_score = max(scores, default=0)
    if max_score <= 0:
        return None
    return frame[[score == max_score for score in scores]].copy()


def _frame_geometry_hash(frame: gpd.GeoDataFrame) -> str:
    if frame.empty:
        return hashlib.sha1(b"empty").hexdigest()
    normalized = frame.to_crs(REQUEST_BBOX_CRS)
    geometries = sorted(geometry.wkb_hex for geometry in normalized.geometry if geometry is not None and not geometry.is_empty)
    bbox = frame_bbox_in_crs(normalized)
    payload = json.dumps(
        {
            "bbox": [round(float(value), 7) for value in bbox] if bbox is not None else None,
            "geometries": geometries,
        },
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()
