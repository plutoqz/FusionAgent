from kg.inmemory_repository import InMemoryKGRepository
from schemas.fusion import JobType


def test_candidate_pattern_and_alternatives() -> None:
    repo = InMemoryKGRepository()
    patterns = repo.get_candidate_patterns(job_type=JobType.building, disaster_type="flood", limit=3)
    assert patterns
    assert patterns[0].job_type == JobType.building

    algo_id = patterns[0].steps[0].algorithm_id
    alternatives = repo.get_alternative_algorithms(algo_id, limit=3)
    assert alternatives


def test_find_transform_path() -> None:
    repo = InMemoryKGRepository()
    path = repo.find_transform_path("dt.raw.vector", "dt.building.bundle", max_depth=3)
    assert path == ["dt.raw.vector", "dt.building.bundle"]

