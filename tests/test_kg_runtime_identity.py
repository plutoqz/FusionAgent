from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

import kg.bootstrap as bootstrap
import kg.factory as factory
import kg.neo4j_repository as neo4j_module
from kg.inmemory_repository import InMemoryKGRepository
from kg.knowledge_release import KnowledgeReleaseError, get_knowledge_identity
from kg.models import DurableLearningRecord, ExecutionFeedback
from kg.neo4j_repository import Neo4jKGRepository
from schemas.fusion import JobType


def _feedback(*, success: bool = True) -> ExecutionFeedback:
    return ExecutionFeedback(
        run_id="run-identity-test",
        job_type=JobType.building,
        trigger_type="disaster_event",
        success=success,
        disaster_type="flood",
        pattern_id="wp.flood.building.safe",
        algorithm_id="algo.fusion.building.safe",
        selected_data_source="upload.bundle",
        repaired=False,
        repair_count=0,
    )


def test_bootstrap_consumes_frozen_entities_without_importing_python_seed() -> None:
    source = Path(bootstrap.__file__).read_text(encoding="utf-8")

    assert "from kg.seed import" not in source
    assert "load_seed_data()" in source


def test_bootstrap_emits_queryable_release_and_tags_static_entities() -> None:
    identity = get_knowledge_identity()

    cypher = bootstrap.build_bootstrap_cypher(graph_namespace="kg-release-test")

    assert "MERGE (release:KnowledgeRelease" in cypher
    assert f'releaseId: "{identity["release_id"]}"' in cypher
    assert f'semanticHash: "{identity["semantic_hash"]}"' in cypher
    assert 'graphNamespace: "kg-release-test"' in cypher
    assert "entityKey" in cypher
    assert "release.relationshipManifest" in cypher


def test_ensure_bootstrap_rejects_same_inventory_with_wrong_release(monkeypatch: pytest.MonkeyPatch) -> None:
    expected = get_knowledge_identity()
    inventory = bootstrap.expected_seed_inventory()
    monkeypatch.setattr(
        bootstrap,
        "inspect_graph_state",
        lambda **_kwargs: {
            "node_count": sum(inventory.values()) + 1,
            "label_counts": [
                {"label": label, "count": count}
                for label, count in inventory.items()
            ],
            "relationship_counts": [],
        },
    )
    monkeypatch.setattr(
        bootstrap,
        "inspect_knowledge_release",
        lambda **_kwargs: {**expected, "semantic_hash": "sha256:" + "f" * 64},
    )
    monkeypatch.setattr(
        bootstrap,
        "apply_bootstrap_cypher",
        lambda **_kwargs: pytest.fail("mismatched release must not be overwritten"),
    )

    with pytest.raises(bootstrap.KnowledgeReleaseStateError, match="does not match"):
        bootstrap.ensure_bootstrap_data(
            uri="bolt://unit.test:7687",
            user="neo4j",
            password="password",
            graph_namespace="fusionagent",
        )


def test_inmemory_identity_is_stable_and_pinned_feedback_does_not_change_planning() -> None:
    repo = InMemoryKGRepository(experience_policy="pinned_snapshot")
    identity_before = repo.get_knowledge_identity()
    pattern_before = repo.get_candidate_patterns(JobType.building, "flood", limit=1)[0].pattern_id

    repo.record_execution_feedback(_feedback())
    repo.record_durable_learning_record(
        DurableLearningRecord(
            record_id="dlr.identity-test",
            run_id="run-identity-test",
            job_type=JobType.building,
            trigger_type="disaster_event",
            success=True,
            disaster_type="flood",
            pattern_id="wp.flood.building.safe",
            created_at="2026-07-28T00:00:00+00:00",
        )
    )

    assert repo.get_knowledge_identity() == identity_before == get_knowledge_identity()
    assert repo.get_candidate_patterns(JobType.building, "flood", limit=1)[0].pattern_id == pattern_before
    assert repo.feedback_history == [_feedback()]
    assert repo.durable_learning_records
    assert repo.list_durable_learning_records(limit=5) == []
    assert repo.summarize_durable_learning_records(limit=5) == {
        "patterns": [],
        "algorithms": [],
        "data_sources": [],
    }


def test_inmemory_pinned_repository_fails_when_required_knowledge_is_deleted() -> None:
    repo = InMemoryKGRepository(experience_policy="pinned_snapshot")
    repo.algorithms.pop("algo.fusion.building.v1")

    with pytest.raises(KnowledgeReleaseError, match="state drifted"):
        repo.build_context(JobType.building, "flood")


def test_neo4j_release_verification_rejects_correct_counts_with_wrong_entity_tag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = get_knowledge_identity()
    repo = Neo4jKGRepository.__new__(Neo4jKGRepository)
    repo.graph_namespace = "fusionagent-test"
    repo._expected_knowledge_identity = identity
    repo.experience_policy = "pinned_snapshot"
    monkeypatch.setattr(neo4j_module, "expected_seed_inventory", lambda: {"Task": 2, "Algorithm": 1})

    def fake_execute(cypher: str, **_params: object) -> list[dict[str, object]]:
        if "MATCH (release:KnowledgeRelease" in cypher:
            return [{**identity, "status": "frozen"}]
        return [
            {"label": "Algorithm", "count": 1, "mismatched_count": 0},
            {"label": "Task", "count": 2, "mismatched_count": 1},
        ]

    repo._execute = fake_execute  # type: ignore[method-assign]

    with pytest.raises(KnowledgeReleaseError, match="release_tags"):
        repo.verify_knowledge_release()


def test_neo4j_release_verification_rejects_property_or_relationship_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = get_knowledge_identity()
    repo = Neo4jKGRepository.__new__(Neo4jKGRepository)
    repo.graph_namespace = "fusionagent-test"
    repo._expected_knowledge_identity = identity
    repo.experience_policy = "pinned_snapshot"
    monkeypatch.setattr(neo4j_module, "expected_seed_inventory", lambda: {"Task": 1})

    def fake_execute(cypher: str, **_params: object) -> list[dict[str, object]]:
        if "MATCH (release:KnowledgeRelease" in cypher and "liveEntityManifest" not in cypher:
            return [{**identity, "status": "frozen"}]
        if "mismatched_count" in cypher:
            return [{"label": "Task", "count": 1, "mismatched_count": 0}]
        return [
            {
                "stored_entity_manifest": ["Task|taskId:task.a|taskName|Frozen name"],
                "live_entity_manifest": ["Task|taskId:task.a|taskName|Mutated name"],
                "stored_relationship_manifest": ["Task|taskId:task.a|REQUIRES|Task|taskId:task.b|||"],
                "live_relationship_manifest": [],
            }
        ]

    repo._execute = fake_execute  # type: ignore[method-assign]

    with pytest.raises(KnowledgeReleaseError, match="manifest mismatch"):
        repo.verify_knowledge_release()


def test_neo4j_from_env_verifies_connectivity_and_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class FakeDriver:
        def verify_connectivity(self) -> None:
            calls.append("connectivity")

        def close(self) -> None:
            calls.append("close")

    class FakeGraphDatabase:
        @staticmethod
        def driver(_uri: str, auth: tuple[str, str]) -> FakeDriver:
            assert auth == ("neo4j", "password")
            return FakeDriver()

    monkeypatch.setitem(sys.modules, "neo4j", types.SimpleNamespace(GraphDatabase=FakeGraphDatabase))
    monkeypatch.setenv("GEOFUSION_NEO4J_URI", "bolt://unit.test:7687")
    monkeypatch.setenv("GEOFUSION_NEO4J_USER", "neo4j")
    monkeypatch.setenv("GEOFUSION_NEO4J_PASSWORD", "password")
    monkeypatch.setattr(
        neo4j_module,
        "resolve_graph_target",
        lambda **_kwargs: {"database_used": "neo4j"},
    )
    monkeypatch.setattr(
        Neo4jKGRepository,
        "verify_knowledge_release",
        lambda self: calls.append("release") or self._expected_identity(),
    )

    repo = Neo4jKGRepository.from_env(
        experience_policy="pinned_snapshot",
        expected_knowledge_identity=get_knowledge_identity(),
    )

    assert calls == ["connectivity", "release"]
    repo.close()
    assert calls[-1] == "close"


def test_strict_factory_does_not_fallback_when_neo4j_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = get_knowledge_identity()

    class Gates:
        @staticmethod
        def runtime_gates() -> dict[str, str]:
            return {
                "experience_policy": "pinned_snapshot",
                "backend_fallback": "forbidden_in_strict_mode",
            }

        @staticmethod
        def backend_fallback_policy() -> str:
            return "forbidden_in_strict_mode"

    monkeypatch.setenv("GEOFUSION_KG_BACKEND", "neo4j")
    monkeypatch.setenv("GEOFUSION_KG_RUNTIME_MODE", "strict")
    monkeypatch.setattr(factory, "default_policy_registry", lambda: Gates())
    monkeypatch.setattr(factory, "get_knowledge_identity", lambda: identity)
    monkeypatch.setattr(
        factory.Neo4jKGRepository,
        "from_env",
        lambda **_kwargs: (_ for _ in ()).throw(ConnectionError("offline")),
    )
    monkeypatch.setattr(
        factory,
        "InMemoryKGRepository",
        lambda **_kwargs: pytest.fail("strict mode must not construct a fallback repository"),
    )

    with pytest.raises(RuntimeError, match="fallback is forbidden"):
        factory.create_kg_repository()


def test_development_factory_uses_policy_authorized_memory_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity = get_knowledge_identity()

    class Gates:
        @staticmethod
        def runtime_gates() -> dict[str, str]:
            return {
                "experience_policy": "pinned_snapshot",
                "backend_fallback": "forbidden_in_strict_mode",
            }

        @staticmethod
        def backend_fallback_policy() -> str:
            return "forbidden_in_strict_mode"

    monkeypatch.setenv("GEOFUSION_KG_BACKEND", "neo4j")
    monkeypatch.setenv("GEOFUSION_KG_RUNTIME_MODE", "development")
    monkeypatch.setattr(factory, "default_policy_registry", lambda: Gates())
    monkeypatch.setattr(factory, "get_knowledge_identity", lambda: identity)
    monkeypatch.setattr(
        factory.Neo4jKGRepository,
        "from_env",
        lambda **_kwargs: (_ for _ in ()).throw(ConnectionError("offline")),
    )

    repo = factory.create_kg_repository()

    assert isinstance(repo, InMemoryKGRepository)
    assert repo.get_knowledge_identity() == identity


def test_research_factory_pins_memory_experience_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEOFUSION_KG_BACKEND", "memory")
    monkeypatch.setenv("GEOFUSION_KG_RUNTIME_MODE", "research")
    monkeypatch.delenv("GEOFUSION_KG_EXPERIENCE_POLICY", raising=False)

    repo = factory.create_kg_repository()

    assert isinstance(repo, InMemoryKGRepository)
    assert repo.experience_policy == "pinned_snapshot"
    assert repo.get_knowledge_identity() == get_knowledge_identity()


def test_memory_and_neo4j_expose_the_same_identity_shape() -> None:
    identity = get_knowledge_identity()
    memory = InMemoryKGRepository(experience_policy="pinned_snapshot")
    neo4j = Neo4jKGRepository.__new__(Neo4jKGRepository)
    neo4j.graph_namespace = "fusionagent-test"
    neo4j._execute = lambda _cypher, **_params: [{**identity, "status": "frozen"}]  # type: ignore[method-assign]

    assert memory.get_knowledge_identity() == neo4j.get_knowledge_identity() == identity
    assert set(identity) == {
        "release_id",
        "ontology_version",
        "knowledge_version",
        "semantic_hash",
        "experience_snapshot_hash",
    }
