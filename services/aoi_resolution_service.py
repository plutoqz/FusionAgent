from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Protocol


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

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidates"] = [candidate.to_dict() for candidate in self.candidates]
        return payload


class AOIAmbiguityError(ValueError):
    def __init__(self, query: str, candidates: tuple[ResolvedAOICandidate, ...]) -> None:
        self.query = query
        self.candidates = candidates
        super().__init__(f"Ambiguous AOI query: {query}")


class AOIResolutionService:
    def __init__(self, *, geocoder: Geocoder) -> None:
        self.geocoder = geocoder

    def resolve(self, user_query: str) -> ResolvedAOI:
        location_query = self.extract_location_query(user_query)
        raw_candidates = list(self.geocoder.search(location_query))
        if not raw_candidates:
            raise ValueError(f"No AOI candidates found for query: {location_query}")

        candidates = tuple(self._deduplicate_candidates(self._normalize_candidate(location_query, raw) for raw in raw_candidates))
        return self._select_candidate(location_query, candidates)

    @staticmethod
    def extract_location_query(user_query: str) -> str:
        query = (user_query or "").strip()
        if not query:
            raise ValueError("AOI query must not be empty.")

        patterns = [
            r"\bfor\s+(?P<location>.+)$",
            r"\bin\s+(?P<location>.+)$",
            r"\baround\s+(?P<location>.+)$",
            r"\bwithin\s+(?P<location>.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, query, flags=re.IGNORECASE)
            if match:
                location = match.group("location").strip(" .,:;")
                if location:
                    return location
        return query

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
            )

        raise AOIAmbiguityError(query, ordered)


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
