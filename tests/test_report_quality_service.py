from __future__ import annotations

from schemas.agent import RunEvent, RunPhase
from schemas.fusion import JobType
from services.report_quality_service import build_report_quality_summary


def test_report_quality_summary_marks_height_raster_participation() -> None:
    summary = build_report_quality_summary(
        job_type=JobType.building.value,
        audit_events=[
            RunEvent(
                timestamp="2026-05-29T00:00:00+00:00",
                kind="task_inputs_resolved",
                phase=RunPhase.running,
                message="inputs",
                details={
                    "component_coverage": {
                        "raw.osm.building": {"feature_count": 2},
                        "raw.google.building_height.raster": {
                            "path": "height.tif",
                            "raster_profile": {"bands": 1},
                        },
                    }
                },
            )
        ],
        source_semantic_contract={
            "height_policy": {
                "raster_height_sources": {"raw.google.building_height.raster": "height.tif"},
                "height_fields": ["height"],
            }
        },
        artifact_metrics={"artifact_validity": True, "feature_count": 2},
        recovery_evidence={},
    )

    assert summary["target_capability"]["target_2_building_height_raster"]["supported"] is True
    assert summary["target_capability"]["target_2_building_height_raster"]["raster_participated"] is True
    assert summary["target_capability"]["target_2_building_height_raster"]["source_ids"] == [
        "raw.google.building_height.raster"
    ]
    assert summary["evidence_readiness_score"] >= 0.8


def test_report_quality_summary_marks_bounded_poi_and_rejects_unbounded_claim() -> None:
    summary = build_report_quality_summary(
        job_type=JobType.poi.value,
        audit_events=[
            RunEvent(
                timestamp="2026-05-29T00:00:00+00:00",
                kind="task_inputs_resolved",
                phase=RunPhase.running,
                message="poi inputs",
                details={
                    "resolved_aoi": {
                        "display_name": "Nairobi, Kenya",
                        "bbox": [36.65, -1.45, 37.10, -1.10],
                    },
                    "component_coverage": {
                        "raw.osm.poi": {"feature_count": 5},
                        "raw.gns.poi": {"feature_count": 2},
                    },
                },
            )
        ],
        source_semantic_contract={"component_source_ids": ["raw.osm.poi", "raw.gns.poi"]},
        artifact_metrics={"artifact_validity": True, "feature_count": 7},
        recovery_evidence={},
    )

    poi = summary["target_capability"]["target_5_bounded_poi"]
    assert poi["supported"] is True
    assert poi["bounded"] is True
    assert poi["aoi_bound"] == [36.65, -1.45, 37.10, -1.10]
    assert poi["source_ids"] == ["raw.gns.poi", "raw.osm.poi"]
    assert poi["unsupported_boundary"] == "unbounded POI entity alignment is unsupported"
