from __future__ import annotations

from kg.neo4j_repository import Neo4jKGRepository


def test_neo4j_repository_is_not_left_abstract_after_repository_contract_changes() -> None:
    assert "get_parameter_specs" not in Neo4jKGRepository.__abstractmethods__


def test_execute_passes_parameters_dict_without_keyword_collision() -> None:
    captured: list[tuple[str, object]] = []

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, cypher: str, parameters=None, **kwargs):
            captured.append((cypher, parameters))
            return [{"ok": True}]

    class FakeDriver:
        def session(self, database=None):
            return FakeSession()

    repo = Neo4jKGRepository.__new__(Neo4jKGRepository)
    repo._driver = FakeDriver()
    repo.database = None

    rows = repo._execute("RETURN $query AS q, $limit AS n", query="building flood", limit=5)

    assert rows == [{"ok": True}]
    assert captured == [("RETURN $query AS q, $limit AS n", {"query": "building flood", "limit": 5})]
