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
