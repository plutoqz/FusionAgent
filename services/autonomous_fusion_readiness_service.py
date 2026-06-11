from __future__ import annotations

from typing import Any, Iterable


REQUIRED_SOURCE_IDS = {
    "building": ["raw.google.building", "raw.microsoft.building", "raw.osm.building", "raw.osm.road"],
    "road": ["raw.osm.road", "raw.microsoft.road"],
    "water": ["raw.osm.water", "raw.hydrolakes.water"],
    "water_polygon": ["raw.osm.water", "raw.hydrolakes.water"],
    "waterways": ["raw.osm.waterways", "raw.hydrorivers.water"],
    "poi": ["raw.gns.poi", "raw.google.poi", "raw.osm.poi"],
    "catalog.flood.building": ["raw.google.building", "raw.microsoft.building", "raw.osm.building", "raw.osm.road"],
    "catalog.earthquake.building": [
        "raw.google.building",
        "raw.microsoft.building",
        "raw.osm.building",
        "raw.osm.road",
    ],
    "catalog.flood.road": ["raw.osm.road", "raw.microsoft.road"],
    "catalog.earthquake.road": ["raw.osm.road", "raw.microsoft.road"],
    "catalog.typhoon.road": ["raw.osm.road", "raw.microsoft.road"],
    "catalog.flood.water": ["raw.osm.water", "raw.hydrolakes.water"],
    "catalog.flood.water_polygon": ["raw.osm.water", "raw.hydrolakes.water"],
    "catalog.flood.waterways": ["raw.osm.waterways", "raw.hydrorivers.water"],
    "catalog.generic.poi": ["raw.gns.poi", "raw.google.poi", "raw.osm.poi"],
}

SOURCE_ID_ALIASES = {
    "raw.geonames.poi": "raw.gns.poi",
}


def classify_autonomous_readiness(
    job_type: str,
    component_coverage: dict[str, Any] | None,
    source_attempts: list[dict[str, Any]] | dict[str, Any] | None,
) -> dict[str, Any]:
    normalized_job_type = str(job_type or "").strip().lower()
    required = list(REQUIRED_SOURCE_IDS.get(normalized_job_type, []))
    if normalized_job_type not in REQUIRED_SOURCE_IDS:
        return {
            "status": "system_failure",
            "job_type": normalized_job_type,
            "required_source_ids": [],
            "missing_required_source_ids": [f"<unknown_job_type:{normalized_job_type}>"],
            "external_uncontrollable_source_ids": [],
        }
    coverage = _canonical_coverage(component_coverage or {})
    attempts = list(_iter_source_attempts(source_attempts))
    missing = [source_id for source_id in required if not _coverage_is_available(coverage.get(source_id))]
    external_missing = [source_id for source_id in missing if _has_external_attempt(source_id, attempts)]

    if not missing:
        status = "full_autonomous_closure"
    elif len(external_missing) == len(missing):
        status = "degraded_external"
    else:
        status = "system_failure"

    return {
        "status": status,
        "job_type": normalized_job_type,
        "required_source_ids": required,
        "missing_required_source_ids": missing,
        "external_uncontrollable_source_ids": external_missing,
    }


def _canonical_coverage(component_coverage: dict[str, Any]) -> dict[str, Any]:
    coverage: dict[str, Any] = {}
    for raw_source_id, payload in component_coverage.items():
        source_id = _canonical_source_id(raw_source_id)
        if source_id not in coverage or _coverage_is_available(payload):
            coverage[source_id] = payload
    return coverage


def _iter_source_attempts(source_attempts: list[dict[str, Any]] | dict[str, Any] | None) -> Iterable[dict[str, Any]]:
    if source_attempts is None:
        return []
    if isinstance(source_attempts, dict):
        raw_attempts = source_attempts.get("attempts") or source_attempts.get("source_attempts") or []
    else:
        raw_attempts = source_attempts
    return [dict(item) for item in raw_attempts if isinstance(item, dict)]


def _coverage_is_available(payload: Any) -> bool:
    if payload is None:
        return False
    feature_count = _optional_int(_coverage_value(payload, "feature_count"))
    if feature_count is not None:
        return feature_count > 0
    return str(_coverage_value(payload, "coverage_status") or "").strip().lower() == "available"


def _has_external_attempt(source_id: str, source_attempts: list[dict[str, Any]]) -> bool:
    canonical_source_id = _canonical_source_id(source_id)
    for attempt in source_attempts:
        if _canonical_source_id(attempt.get("source_id")) != canonical_source_id:
            continue
        if attempt.get("external_uncontrollable") is True:
            return True
    return False


def _coverage_value(payload: Any, key: str) -> Any:
    if isinstance(payload, dict):
        return payload.get(key)
    return getattr(payload, key, None)


def _canonical_source_id(source_id: Any) -> str:
    normalized = str(source_id or "").strip().lower()
    return SOURCE_ID_ALIASES.get(normalized, normalized)


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
