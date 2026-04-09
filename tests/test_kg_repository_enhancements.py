from kg.inmemory_repository import InMemoryKGRepository
from kg.models import ExecutionFeedback
from schemas.fusion import JobType


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
