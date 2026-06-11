from __future__ import annotations

import json
from pathlib import Path


def test_build_source_materialization_manifest_records_fault_and_provider_attempts() -> None:
    from services.source_materialization_manifest_service import build_source_materialization_manifest

    manifest = build_source_materialization_manifest(
        source_id="catalog.flood.water",
        selected_source_id="catalog.flood.water",
        source_mode="downloaded",
        cache_hit=False,
        version_token="v1",
        target_crs="EPSG:32643",
        requested_bbox=(10, 10, 11, 11),
        materialized_bbox=(10.0, 10.0, 11.0, 11.0),
        clipped_to_aoi=True,
        component_coverage={"raw.osm.water": {"coverage_status": "available", "feature_count": 4}},
        provider_attempts=[{"source_id": "catalog.flood.water", "status": "failed", "fault_class": "SOURCE_MISSING"}],
        source_attempts_path="source_attempts.json",
        coverage_state="partial",
        degradation={
            "degraded_source_ids": ["raw.gns.water"],
            "external_uncontrollable_source_ids": ["raw.gns.water"],
        },
        fault={"fault_class": "SOURCE_MISSING", "fault_message": "missing water", "recoverable": True},
    )

    assert manifest["source_id"] == "catalog.flood.water"
    assert manifest["selected_source_id"] == "catalog.flood.water"
    assert manifest["source_mode"] == "downloaded"
    assert manifest["cache_hit"] is False
    assert manifest["version_token"] == "v1"
    assert manifest["target_crs"] == "EPSG:32643"
    assert manifest["requested_bbox"] == [10.0, 10.0, 11.0, 11.0]
    assert manifest["materialized_bbox"] == [10.0, 10.0, 11.0, 11.0]
    assert manifest["clipped_to_aoi"] is True
    assert manifest["component_coverage"]["raw.osm.water"]["feature_count"] == 4
    assert manifest["provider_attempts"][0]["fault_class"] == "SOURCE_MISSING"
    assert manifest["source_attempts_path"] == "source_attempts.json"
    assert manifest["coverage_state"] == "partial"
    assert manifest["degradation"] == {
        "degraded_source_ids": ["raw.gns.water"],
        "external_uncontrollable_source_ids": ["raw.gns.water"],
    }
    assert manifest["fault"] == {
        "fault_class": "SOURCE_MISSING",
        "fault_message": "missing water",
        "recoverable": True,
    }


def test_write_source_materialization_manifest_persists_json(tmp_path: Path) -> None:
    from services.source_materialization_manifest_service import write_source_materialization_manifest

    path = write_source_materialization_manifest(
        tmp_path / "run" / "source_materialization_manifest.json",
        {
            "source_id": "catalog.task.building.default",
            "selected_source_id": "catalog.task.building.default",
            "source_mode": "cache_reused",
            "cache_hit": True,
        },
    )

    assert path == tmp_path / "run" / "source_materialization_manifest.json"
    assert json.loads(path.read_text(encoding="utf-8"))["source_mode"] == "cache_reused"
