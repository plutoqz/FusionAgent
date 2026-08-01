from __future__ import annotations

import os

import pytest

from kg.bootstrap import prepare_local_neo4j
from kg.inmemory_repository import InMemoryKGRepository
from kg.knowledge_release import get_knowledge_identity
from kg.neo4j_repository import Neo4jKGRepository
from schemas.fusion import JobType


URI = os.getenv("GEOFUSION_K4_NEO4J_URI")
USER = os.getenv("GEOFUSION_K4_NEO4J_USER", "neo4j")
PASSWORD = os.getenv("GEOFUSION_K4_NEO4J_PASSWORD", "k4-validation")

pytestmark = pytest.mark.skipif(
    not URI,
    reason="set GEOFUSION_K4_NEO4J_URI to run the real Neo4j K4 parity check",
)


def _pattern_projection(context):
    return [
        (
            pattern.pattern_id,
            [
                (
                    step.order,
                    step.algorithm_id,
                    step.data_source_id,
                    step.input_data_type,
                    step.output_data_type,
                )
                for step in pattern.steps
            ],
        )
        for pattern in context.patterns
    ]


def test_real_neo4j_matches_pinned_memory_runtime_context() -> None:
    summary = prepare_local_neo4j(
        uri=str(URI),
        user=USER,
        password=PASSWORD,
        reset_managed=True,
    )
    assert summary["kg_contract_ok"] is True
    assert summary["knowledge_manifests_match"] is True

    memory = InMemoryKGRepository(experience_policy="pinned_snapshot")
    neo4j = Neo4jKGRepository(
        uri=str(URI),
        user=USER,
        password=PASSWORD,
        database=summary["database_used"],
        graph_namespace=summary["graph_namespace"],
        experience_policy="pinned_snapshot",
        expected_knowledge_identity=get_knowledge_identity(),
    )
    try:
        neo4j.verify_connectivity()
        assert neo4j.verify_knowledge_release() == memory.get_knowledge_identity()
        for job_type, disaster_type in (
            (JobType.building, "flood"),
            (JobType.road, "earthquake"),
            (JobType.water, "flood"),
            (JobType.poi, None),
        ):
            memory_context = memory.build_context(job_type, disaster_type)
            neo4j_context = neo4j.build_context(job_type, disaster_type)
            assert _pattern_projection(neo4j_context) == _pattern_projection(memory_context)
            assert sorted(neo4j_context.algorithms) == sorted(memory_context.algorithms)
            assert [source.source_id for source in neo4j_context.data_sources] == [
                source.source_id for source in memory_context.data_sources
            ]
    finally:
        neo4j.close()
