from __future__ import annotations

import sys
import types

from kg.bootstrap import (
    apply_bootstrap_cypher,
    build_bootstrap_cypher,
    ensure_bootstrap_data,
)


def test_bootstrap_cypher_contains_schema_and_seed_entities() -> None:
    cypher = build_bootstrap_cypher()

    assert "workflow_pattern_pattern_id" in cypher
    assert "algorithm_algo_id" in cypher
    assert "datasource_source_id" in cypher
    assert "CREATE FULLTEXT INDEX wp_search" in cypher
    assert "MERGE (wp:WorkflowPattern" in cypher
    assert "MERGE (algo:Algorithm" in cypher
    assert "MERGE (ds:DataSource" in cypher
    assert "MERGE (dt:DataType" in cypher
    assert "MERGE (run:WorkflowInstance" not in cypher


def test_apply_bootstrap_cypher_uses_home_database_by_default(monkeypatch) -> None:
    executed_statements: list[str] = []
    session_databases: list[object] = []

    class FakeSession:
        def __init__(self, database):
            self.database = database

        def __enter__(self):
            session_databases.append(self.database)
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, statement: str):
            executed_statements.append(statement)
            return []

    class FakeDriver:
        def session(self, database=None):
            return FakeSession(database)

        def close(self) -> None:
            return None

    class FakeGraphDatabase:
        @staticmethod
        def driver(uri, auth):
            assert uri == "bolt://localhost:7687"
            assert auth == ("neo4j", "password")
            return FakeDriver()

    monkeypatch.setitem(sys.modules, "neo4j", types.SimpleNamespace(GraphDatabase=FakeGraphDatabase))

    apply_bootstrap_cypher(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="password",
        cypher="CREATE CONSTRAINT foo IF NOT EXISTS FOR (n:Foo) REQUIRE n.id IS UNIQUE; MERGE (n:Foo {id: '1'});",
    )

    assert session_databases == [None]
    assert executed_statements == [
        "CREATE CONSTRAINT foo IF NOT EXISTS FOR (n:Foo) REQUIRE n.id IS UNIQUE",
        "MERGE (n:Foo {id: '1'})",
    ]


def test_ensure_bootstrap_data_applies_seed_only_when_missing(monkeypatch) -> None:
    executed_statements: list[str] = []

    class FakeResult:
        def __init__(self, count: int):
            self._count = count

        def single(self):
            return {"count": self._count}

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, statement: str):
            self.calls += 1
            if "MATCH (wp:WorkflowPattern)" in statement:
                return FakeResult(0)
            executed_statements.append(statement)
            return []

    class FakeDriver:
        def session(self, database=None):
            return FakeSession()

        def close(self) -> None:
            return None

    class FakeGraphDatabase:
        @staticmethod
        def driver(uri, auth):
            return FakeDriver()

    monkeypatch.setitem(sys.modules, "neo4j", types.SimpleNamespace(GraphDatabase=FakeGraphDatabase))

    applied = ensure_bootstrap_data(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="password",
        cypher="MERGE (n:Foo {id: '1'});",
    )

    assert applied is True
    assert executed_statements == ["MERGE (n:Foo {id: '1'})"]
