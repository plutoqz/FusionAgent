from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field
from utils.crs import normalize_target_crs


def _utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_dt(value: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(value)
    except Exception:  # noqa: BLE001
        return None
    if dt.tzinfo is None:
        # Treat naive timestamps as UTC to keep registry behavior deterministic.
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _norm_token(value: object | None) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "value"):
        try:
            value = getattr(value, "value")
        except Exception:  # noqa: BLE001
            pass
    text = str(value).strip()
    return text or None


def _norm_crs(value: object | None) -> Optional[str]:
    token = _norm_token(value)
    if token is None:
        return None
    try:
        return normalize_target_crs(token)
    except Exception:  # noqa: BLE001
        return None


def _norm_field_set(fields: Iterable[str]) -> set[str]:
    normalized: set[str] = set()
    for item in fields or []:
        token = str(item).strip()
        if token:
            normalized.add(token)
    return normalized


BBox = Tuple[float, float, float, float]


def _as_bbox(value: Sequence[float] | None) -> Optional[BBox]:
    if value is None:
        return None
    if len(value) != 4:
        return None
    try:
        minx, miny, maxx, maxy = (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
    except Exception:  # noqa: BLE001
        return None
    if maxx < minx or maxy < miny:
        return None
    return (minx, miny, maxx, maxy)


def _bbox_contains(outer: BBox, inner: BBox) -> bool:
    ominx, ominy, omaxx, omaxy = outer
    iminx, iminy, imaxx, imaxy = inner
    return ominx <= iminx and ominy <= iminy and omaxx >= imaxx and omaxy >= imaxy


class ArtifactRecord(BaseModel):
    """
    A persisted fusion artifact entry.

    Spatial behavior:
    - If a lookup request provides a bbox, we require the artifact bbox to fully contain
      the request bbox. This is intentionally conservative to avoid misleading "matches"
      where an artifact only partially covers the requested area.
    - If either side lacks a bbox, bbox-based matching is not performed (and if the
      request had a bbox, the artifact is treated as non-matching).
    """

    artifact_id: str
    artifact_path: str

    job_type: str
    disaster_type: Optional[str] = None

    created_at: str
    output_fields: List[str] = Field(default_factory=list)
    output_data_type: Optional[str] = None
    target_crs: Optional[str] = None
    schema_policy_id: Optional[str] = None
    compatibility_basis: Optional[str] = None

    bbox: Optional[Tuple[float, float, float, float]] = None
    meta: Dict[str, Any] = Field(default_factory=dict)


class ArtifactLookupRequest(BaseModel):
    job_type: Optional[str] = None
    disaster_type: Optional[str] = None

    max_age_seconds: Optional[int] = None
    required_fields: List[str] = Field(default_factory=list)
    required_output_type: Optional[str] = None
    required_target_crs: Optional[str] = None
    required_meta: Dict[str, Any] = Field(default_factory=dict)

    bbox: Optional[Tuple[float, float, float, float]] = None


def _meta_contains(actual: Dict[str, Any], required: Dict[str, Any]) -> bool:
    for key, value in (required or {}).items():
        if actual.get(key) != value:
            return False
    return True


@dataclass(frozen=True)
class _IndexPayload:
    version: int
    records: List[ArtifactRecord]


class ArtifactRegistry:
    """
    JSON index-backed registry.

    The index format is a single JSON file:
      {"version": 1, "records": [ ...ArtifactRecord... ]}
    """

    def __init__(self, index_path: Path) -> None:
        self.index_path = Path(index_path)
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def register(self, record: ArtifactRecord) -> None:
        with self._lock:
            payload = self._load()
            updated: List[ArtifactRecord] = []
            replaced = False
            for existing in payload.records:
                if existing.artifact_id == record.artifact_id:
                    updated.append(record)
                    replaced = True
                else:
                    updated.append(existing)
            if not replaced:
                updated.append(record)

            # Keep deterministic ordering: newest first.
            updated.sort(key=lambda r: (r.created_at or ""), reverse=True)
            self._save(_IndexPayload(version=payload.version, records=updated))

    def find_reusable(self, request: ArtifactLookupRequest, now: Optional[datetime] = None) -> Optional[ArtifactRecord]:
        now_dt = now or _utc_now_dt()
        with self._lock:
            payload = self._load()

        want_job_type = _norm_token(request.job_type)
        want_disaster = _norm_token(request.disaster_type)
        want_fields = _norm_field_set(request.required_fields)
        want_output_type = _norm_token(request.required_output_type)
        want_target_crs = _norm_crs(request.required_target_crs)
        want_meta = dict(request.required_meta or {})
        want_bbox = _as_bbox(request.bbox)

        max_age_seconds = request.max_age_seconds
        if max_age_seconds is not None and max_age_seconds < 0:
            max_age_seconds = 0

        candidates: List[tuple[datetime, ArtifactRecord]] = []
        for record in payload.records:
            if want_job_type is not None and _norm_token(record.job_type) != want_job_type:
                continue
            if want_disaster is not None and (_norm_token(record.disaster_type) or "").lower() != want_disaster.lower():
                continue
            if want_output_type is not None and _norm_token(record.output_data_type) != want_output_type:
                continue
            if want_target_crs is not None and _norm_crs(record.target_crs) != want_target_crs:
                continue
            if want_meta and not _meta_contains(record.meta, want_meta):
                continue

            created_dt = _parse_iso_dt(record.created_at)
            if created_dt is None:
                continue

            if max_age_seconds is not None:
                age_seconds = (now_dt - created_dt).total_seconds()
                if age_seconds > float(max_age_seconds):
                    continue

            if want_fields:
                have_fields = _norm_field_set(record.output_fields)
                if not want_fields.issubset(have_fields):
                    continue

            if want_bbox is not None:
                have_bbox = _as_bbox(record.bbox)
                if have_bbox is None:
                    continue
                if not _bbox_contains(have_bbox, want_bbox):
                    continue

            candidates.append((created_dt, record))

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def list_reusable(
        self,
        request: ArtifactLookupRequest,
        *,
        now: Optional[datetime] = None,
        limit: int = 5,
    ) -> List[ArtifactRecord]:
        """
        Return reusable candidates ordered by recency (newest first).

        This is a convenience API for planner-context enrichment. It shares the same
        matching semantics as find_reusable(), but returns up to `limit` items.
        """
        if limit <= 0:
            return []

        now_dt = now or _utc_now_dt()
        with self._lock:
            payload = self._load()

        want_job_type = _norm_token(request.job_type)
        want_disaster = _norm_token(request.disaster_type)
        want_fields = _norm_field_set(request.required_fields)
        want_output_type = _norm_token(request.required_output_type)
        want_target_crs = _norm_crs(request.required_target_crs)
        want_meta = dict(request.required_meta or {})
        want_bbox = _as_bbox(request.bbox)

        max_age_seconds = request.max_age_seconds
        if max_age_seconds is not None and max_age_seconds < 0:
            max_age_seconds = 0

        candidates: List[tuple[datetime, ArtifactRecord]] = []
        for record in payload.records:
            if want_job_type is not None and _norm_token(record.job_type) != want_job_type:
                continue
            if want_disaster is not None and (_norm_token(record.disaster_type) or "").lower() != want_disaster.lower():
                continue
            if want_output_type is not None and _norm_token(record.output_data_type) != want_output_type:
                continue
            if want_target_crs is not None and _norm_crs(record.target_crs) != want_target_crs:
                continue
            if want_meta and not _meta_contains(record.meta, want_meta):
                continue

            created_dt = _parse_iso_dt(record.created_at)
            if created_dt is None:
                continue

            if max_age_seconds is not None:
                age_seconds = (now_dt - created_dt).total_seconds()
                if age_seconds > float(max_age_seconds):
                    continue

            if want_fields:
                have_fields = _norm_field_set(record.output_fields)
                if not want_fields.issubset(have_fields):
                    continue

            if want_bbox is not None:
                have_bbox = _as_bbox(record.bbox)
                if have_bbox is None:
                    continue
                if not _bbox_contains(have_bbox, want_bbox):
                    continue

            candidates.append((created_dt, record))

        if not candidates:
            return []
        candidates.sort(key=lambda item: item[0], reverse=True)
        return [record for _dt, record in candidates[:limit]]

    def _load(self) -> _IndexPayload:
        if not self.index_path.exists():
            return _IndexPayload(version=1, records=[])
        try:
            raw = json.loads(self.index_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return _IndexPayload(version=1, records=[])

        version = int(raw.get("version", 1)) if isinstance(raw, dict) else 1
        items = raw.get("records", []) if isinstance(raw, dict) else []
        records: List[ArtifactRecord] = []
        if isinstance(items, list):
            for item in items:
                try:
                    records.append(ArtifactRecord.model_validate(item))
                except Exception:  # noqa: BLE001
                    continue
        return _IndexPayload(version=version, records=records)

    def _save(self, payload: _IndexPayload) -> None:
        data = {
            "version": payload.version,
            "records": [r.model_dump(mode="json") for r in payload.records],
        }
        tmp_path = self.index_path.with_suffix(self.index_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
        tmp_path.replace(self.index_path)
