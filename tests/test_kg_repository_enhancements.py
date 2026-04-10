from kg.inmemory_repository import InMemoryKGRepository
from kg.models import DurableLearningRecord, DurableLearningSummary, ExecutionFeedback
from schemas.fusion import JobType


def test_build_context_exposes_task_nodes_and_scenario_profiles() -> None:
    repo = InMemoryKGRepository()

    context = repo.build_context(job_type=JobType.building, disaster_type="flood")

    assert context.task_nodes
    assert any(task.task_id == "task.building.fusion" for task in context.task_nodes)
    assert context.scenario_profiles
    assert any(profile.profile_id == "scenario.flood.default" for profile in context.scenario_profiles)


def test_inmemory_repository_returns_ranked_data_sources() -> None:
    repo = InMemoryKGRepository()

    sources = repo.get_candidate_data_sources(
        job_type=JobType.building,
        disaster_type="flood",
        required_type="dt.building.bundle",
        limit=3,
    )

    assert sources
    assert sources[0].source_id == "upload.bundle"
    assert all("dt.building.bundle" in source.supported_types for source in sources)


def test_execution_feedback_changes_pattern_ranking() -> None:
    repo = InMemoryKGRepository()

    patterns_before = repo.get_candidate_patterns(job_type=JobType.building, disaster_type="flood", limit=3)
    assert patterns_before[0].pattern_id == "wp.flood.building.default"

    repo.record_execution_feedback(
        ExecutionFeedback(
            run_id="run-1",
            job_type=JobType.building,
            disaster_type="flood",
            trigger_type="disaster_event",
            success=True,
            pattern_id="wp.flood.building.safe",
            algorithm_id="algo.fusion.building.safe",
            selected_data_source="upload.bundle",
            repaired=False,
            repair_count=0,
            failure_reason=None,
        )
    )

    patterns_after = repo.get_candidate_patterns(job_type=JobType.building, disaster_type="flood", limit=3)
    assert patterns_after[0].pattern_id == "wp.flood.building.safe"


def test_search_knowledge_returns_algorithm_and_pattern_hits() -> None:
    repo = InMemoryKGRepository()

    hits = repo.search_knowledge("safe building", limit=5)

    assert hits
    assert {hit["kind"] for hit in hits} >= {"algorithm", "pattern"}


def test_repository_exposes_multiple_disaster_specific_pattern_candidates() -> None:
    repo = InMemoryKGRepository()

    building_patterns = repo.get_candidate_patterns(job_type=JobType.building, disaster_type="earthquake", limit=4)
    road_patterns = repo.get_candidate_patterns(job_type=JobType.road, disaster_type="typhoon", limit=4)

    assert len(building_patterns) >= 3
    assert len(road_patterns) >= 3
    assert any(pattern.pattern_id == "wp.earthquake.building.default" for pattern in building_patterns)
    assert any(pattern.pattern_id == "wp.earthquake.building.safe" for pattern in building_patterns)
    assert any(pattern.pattern_id == "wp.typhoon.road.default" for pattern in road_patterns)
    assert any(pattern.pattern_id == "wp.typhoon.road.safe" for pattern in road_patterns)


def test_repository_exposes_richer_data_source_signals_for_current_themes() -> None:
    repo = InMemoryKGRepository()

    building_sources = repo.get_candidate_data_sources(
        job_type=JobType.building,
        disaster_type="earthquake",
        required_type="dt.building.bundle",
        limit=4,
    )
    road_sources = repo.get_candidate_data_sources(
        job_type=JobType.road,
        disaster_type="typhoon",
        required_type="dt.road.bundle",
        limit=4,
    )

    building_ids = {source.source_id for source in building_sources}
    road_ids = {source.source_id for source in road_sources}

    assert "catalog.earthquake.building" in building_ids
    assert "catalog.typhoon.road" in road_ids

    earthquake_building = next(source for source in building_sources if source.source_id == "catalog.earthquake.building")
    typhoon_road = next(source for source in road_sources if source.source_id == "catalog.typhoon.road")

    assert earthquake_building.source_kind == "catalog"
    assert earthquake_building.quality_tier == "curated"
    assert earthquake_building.freshness_category == "event_snapshot"
    assert earthquake_building.freshness_hours == 96
    assert earthquake_building.freshness_score == 0.71
    assert earthquake_building.supported_job_types == ["building"]
    assert earthquake_building.supported_geometry_types == ["polygon"]

    assert typhoon_road.source_kind == "catalog"
    assert typhoon_road.quality_tier == "curated"
    assert typhoon_road.freshness_category == "event_snapshot"
    assert typhoon_road.freshness_hours == 48
    assert typhoon_road.supported_job_types == ["road"]
    assert typhoon_road.supported_geometry_types == ["line"]


def test_inmemory_repository_persists_and_filters_durable_learning_records() -> None:
    repo = InMemoryKGRepository()

    repo.record_durable_learning_record(
        DurableLearningRecord(
            record_id="dlr-building-success",
            run_id="run-building-success",
            job_type=JobType.building,
            trigger_type="disaster_event",
            success=True,
            disaster_type="flood",
            pattern_id="wp.flood.building.default",
            algorithm_id="algo.fusion.building.v1",
            selected_data_source="upload.bundle",
            output_data_type="dt.building.fused",
            target_crs="EPSG:32643",
            repaired=False,
            repair_count=0,
            plan_revision=1,
            created_at="2026-04-09T01:00:00+00:00",
        )
    )
    repo.record_durable_learning_record(
        DurableLearningRecord(
            record_id="dlr-road-failure",
            run_id="run-road-failure",
            job_type=JobType.road,
            trigger_type="disaster_event",
            success=False,
            disaster_type="flood",
            pattern_id="wp.flood.road.default",
            algorithm_id="algo.fusion.road.v1",
            selected_data_source="catalog.typhoon.road",
            output_data_type="dt.road.fused",
            target_crs="EPSG:32643",
            repaired=True,
            repair_count=2,
            failure_reason="RuntimeError: still failing",
            plan_revision=2,
            created_at="2026-04-09T02:00:00+00:00",
        )
    )

    building_records = repo.list_durable_learning_records(job_type=JobType.building, limit=5)
    assert [record.record_id for record in building_records] == ["dlr-building-success"]
    assert building_records[0].output_data_type == "dt.building.fused"

    failed_records = repo.list_durable_learning_records(success=False, limit=5)
    assert [record.record_id for record in failed_records] == ["dlr-road-failure"]
    assert failed_records[0].failure_reason == "RuntimeError: still failing"


def test_repository_aggregates_durable_learning_records_for_retrieval() -> None:
    repo = InMemoryKGRepository()

    repo.record_durable_learning_record(
        DurableLearningRecord(
            record_id="dlr-1",
            run_id="run-1",
            job_type=JobType.building,
            trigger_type="disaster_event",
            success=True,
            disaster_type="flood",
            pattern_id="wp.flood.building.default",
            algorithm_id="algo.fusion.building.v1",
            selected_data_source="upload.bundle",
            output_data_type="dt.building.fused",
            target_crs="EPSG:32643",
            repaired=False,
            repair_count=0,
            plan_revision=1,
            created_at="2026-04-09T01:00:00+00:00",
        )
    )
    repo.record_durable_learning_record(
        DurableLearningRecord(
            record_id="dlr-2",
            run_id="run-2",
            job_type=JobType.building,
            trigger_type="disaster_event",
            success=False,
            disaster_type="flood",
            pattern_id="wp.flood.building.default",
            algorithm_id="algo.fusion.building.v1",
            selected_data_source="upload.bundle",
            output_data_type="dt.building.fused",
            target_crs="EPSG:32643",
            repaired=True,
            repair_count=2,
            failure_reason="RuntimeError: failed",
            plan_revision=2,
            created_at="2026-04-09T02:00:00+00:00",
        )
    )

    summary = repo.summarize_durable_learning_records(job_type=JobType.building, disaster_type="flood", limit=5)

    assert summary["patterns"] == [
        DurableLearningSummary(
            entity_kind="pattern",
            entity_id="wp.flood.building.default",
            job_type=JobType.building,
            disaster_type="flood",
            total_runs=2,
            success_count=1,
            failure_count=1,
            repaired_count=1,
            last_run_at="2026-04-09T02:00:00+00:00",
            last_failure_reason="RuntimeError: failed",
        )
    ]
    assert summary["algorithms"][0].entity_id == "algo.fusion.building.v1"
    assert summary["data_sources"][0].entity_id == "upload.bundle"
