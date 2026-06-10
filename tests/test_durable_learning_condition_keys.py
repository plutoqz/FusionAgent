from __future__ import annotations

from kg.models import DurableLearningRecord
from kg.repository import _learning_condition_key
from schemas.fusion import JobType


def test_learning_condition_key_includes_architecture_mvp_dimensions() -> None:
    record = DurableLearningRecord(
        record_id="dlr-1",
        run_id="run-1",
        job_type=JobType.road,
        trigger_type="user_query",
        success=False,
        disaster_type="flood",
        pattern_id="wp.road.v7",
        algorithm_id="algo.fusion.road.conflation.v7",
        failure_reason="SOURCE_DOWNLOAD_FAILED",
        metadata={
            "task_kind": "road",
            "aoi_size_bucket": "medium",
            "source_coverage_bucket": "partial",
            "failure_category": "SOURCE_DOWNLOAD_FAILED",
            "quality_outcome": "quality_gate_failed",
        },
    )

    key = _learning_condition_key(record, "wp.road.v7")

    assert key == (
        "task=road|entity=wp.road.v7|aoi=medium|source_coverage=partial|"
        "failure=SOURCE_DOWNLOAD_FAILED|quality=quality_gate_failed"
    )


def test_learning_condition_key_has_stable_defaults_for_legacy_records() -> None:
    record = DurableLearningRecord(
        record_id="dlr-legacy",
        run_id="run-legacy",
        job_type=JobType.building,
        trigger_type="user_query",
        success=True,
        algorithm_id="algo.fusion.building.v1",
        metadata={},
    )

    key = _learning_condition_key(record, "algo.fusion.building.v1")

    assert key == (
        "task=building|entity=algo.fusion.building.v1|aoi=unknown|"
        "source_coverage=unknown|failure=none|quality=unknown"
    )
