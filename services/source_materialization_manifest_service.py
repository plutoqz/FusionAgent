from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence


def build_source_materialization_manifest(
    *,
    source_id: str,
    selected_source_id: str | None,
    source_mode: str,
    cache_hit: bool,
    version_token: str | None,
    target_crs: str | None,
    requested_bbox: Sequence[float] | None = None,
    materialized_bbox: Sequence[float] | None = None,
    clipped_to_aoi: bool = False,
    component_coverage: dict[str, object] | None = None,
    provider_attempts: list[dict[str, object]] | None = None,
    fault: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "selected_source_id": selected_source_id or source_id,
        "source_mode": source_mode,
        "cache_hit": bool(cache_hit),
        "version_token": version_token,
        "target_crs": target_crs,
        "requested_bbox": _bbox_payload(requested_bbox),
        "materialized_bbox": _bbox_payload(materialized_bbox),
        "clipped_to_aoi": bool(clipped_to_aoi),
        "component_coverage": dict(component_coverage or {}),
        "provider_attempts": list(provider_attempts or []),
        "fault": _fault_payload(fault),
    }


def write_source_materialization_manifest(path: Path, manifest: dict[str, object]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _bbox_payload(value: Sequence[float] | None) -> list[float] | None:
    if value is None or len(value) != 4:
        return None
    return [float(item) for item in value]


def _fault_payload(value: dict[str, object] | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "fault_class": str(value.get("fault_class") or ""),
        "fault_message": str(value.get("fault_message") or ""),
        "recoverable": bool(value.get("recoverable")),
    }
