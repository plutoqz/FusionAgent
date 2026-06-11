from __future__ import annotations

from services.autonomous_fusion_readiness_service import classify_autonomous_readiness


def test_autonomous_closure_matrix_defines_required_sources_for_all_core_tasks() -> None:
    cases = {
        "building": ["raw.google.building", "raw.microsoft.building", "raw.osm.building", "raw.osm.road"],
        "road": ["raw.osm.road", "raw.microsoft.road"],
        "poi": ["raw.gns.poi", "raw.google.poi", "raw.osm.poi"],
        "water": ["raw.osm.water", "raw.hydrolakes.water"],
        "waterways": ["raw.osm.waterways", "raw.hydrorivers.water"],
    }

    for job_type, source_ids in cases.items():
        result = classify_autonomous_readiness(
            job_type=job_type,
            component_coverage={
                source_id: {"coverage_status": "available", "feature_count": 1}
                for source_id in source_ids
            },
            source_attempts=[],
        )
        assert result["required_source_ids"] == source_ids, job_type
        assert result["status"] == "full_autonomous_closure", job_type
