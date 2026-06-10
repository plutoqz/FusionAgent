from __future__ import annotations

from services.agent_run_service import _build_durable_learning_condition_metadata


def test_durable_learning_condition_metadata_buckets_runtime_context() -> None:
    metadata = _build_durable_learning_condition_metadata(
        task_kind="road",
        requested_bbox=[0.0, 0.0, 0.4, 0.4],
        component_coverage={
            "raw.osm.road": {"coverage_status": "available"},
            "raw.overture.transportation": {"coverage_status": "missing"},
        },
        failure_category="SOURCE_MISSING",
        quality_gate_accepted=False,
    )

    assert metadata["task_kind"] == "road"
    assert metadata["aoi_size_bucket"] in {"small", "medium", "large"}
    assert metadata["source_coverage_bucket"] == "partial"
    assert metadata["failure_category"] == "SOURCE_MISSING"
    assert metadata["quality_outcome"] == "quality_gate_failed"
