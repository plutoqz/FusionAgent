from __future__ import annotations

import sys
import types
from pathlib import Path

from kg.bootstrap import (
    MANAGED_LABEL,
    apply_bootstrap_cypher,
    build_bootstrap_cypher,
    ensure_bootstrap_data,
    expected_seed_inventory,
    resolve_graph_target,
)


def test_bootstrap_cypher_contains_schema_and_seed_entities() -> None:
    cypher = build_bootstrap_cypher()

    assert "workflow_pattern_pattern_id" in cypher
    assert "algorithm_algo_id" in cypher
    assert "algorithm_parameter_spec_spec_id" in cypher
    assert "datasource_source_id" in cypher
    assert "CREATE FULLTEXT INDEX wp_search" in cypher
    assert f":{MANAGED_LABEL}" in cypher
    assert "MERGE (wp:WorkflowPattern" in cypher
    assert "MERGE (algo:Algorithm" in cypher
    assert "MERGE (ps:AlgorithmParameterSpec" in cypher
    assert "HAS_PARAMETER_SPEC" in cypher
    assert "MERGE (ds:DataSource" in cypher
    assert "MERGE (dt:DataType" in cypher
    assert f"SET wp:{MANAGED_LABEL}" in cypher
    assert f"SET algo:{MANAGED_LABEL}" in cypher
    assert "MERGE (run:WorkflowInstance" not in cypher


def test_bootstrap_cypher_contains_water_vertical_slice() -> None:
    cypher = build_bootstrap_cypher()

    assert "dt.water.bundle" in cypher
    assert "dt.water.fused" in cypher
    assert "task.water.fusion" in cypher
    assert "algo.fusion.water.v1" in cypher
    assert "current uploaded-only runtime columns" not in cypher
    assert "shared bundle runtime columns" in cypher
    assert "wp.flood.water.default" in cypher
    assert "osp.water.fused.v1" in cypher


def test_checked_in_bootstrap_cypher_stays_in_sync_with_generator_and_trajectory_seam() -> None:
    checked_in = Path("kg/bootstrap/neo4j_bootstrap.cypher").read_text(encoding="utf-8")
    generated = build_bootstrap_cypher()

    assert checked_in == generated
    assert 'typeId: "dt.trajectory.raw"' in checked_in
    assert 'typeId: "dt.road.candidate"' in checked_in
    assert 'taskId: "task.trajectory_to_road"' in checked_in
    assert 'algoId: "algo.transform.trajectory_to_road_candidate"' in checked_in
    assert 'MATCH (src:DataType:FusionAgentManaged {typeId: "dt.trajectory.raw"}), (dst:DataType:FusionAgentManaged {typeId: "dt.road.candidate"})' in checked_in


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
        def __init__(self, rows=None, single_row=None):
            self._rows = rows or []
            self._single_row = single_row

        def single(self):
            return self._single_row

        def __iter__(self):
            return iter(self._rows)

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, statement: str, **params):
            self.calls += 1
            normalized = " ".join(statement.split())
            if "MATCH (n:FusionAgentManaged) RETURN count(n) AS count" in normalized:
                return FakeResult(single_row={"count": 0})
            if "UNWIND [label IN labels(n) WHERE label <> $managed_label] AS label" in normalized:
                assert params["managed_label"] == MANAGED_LABEL
                return FakeResult(rows=[])
            if "MATCH (:FusionAgentManaged)-[r]->(:FusionAgentManaged)" in normalized:
                return FakeResult(rows=[])
            executed_statements.append(statement)
            return FakeResult(rows=[])

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


def test_expected_seed_inventory_matches_static_bootstrap_contract() -> None:
    inventory = expected_seed_inventory()

    assert inventory == {
        "DataType": 27,
        "Task": 10,
        "Algorithm": 33,
        "AlgorithmParameterSpec": 44,
        "DataSource": 22,
        "ScenarioProfile": 4,
        "OutputSchemaPolicy": 4,
        "WorkflowPattern": 14,
    }


def test_ensure_bootstrap_data_applies_seed_when_non_pattern_seed_labels_are_missing(monkeypatch) -> None:
    executed_statements: list[str] = []

    class FakeResult:
        def __init__(self, rows=None, single_row=None):
            self._rows = rows or []
            self._single_row = single_row

        def single(self):
            return self._single_row

        def __iter__(self):
            return iter(self._rows)

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, statement: str, **params):
            normalized = " ".join(statement.split())
            if "MATCH (n:FusionAgentManaged) RETURN count(n) AS count" in normalized:
                return FakeResult(single_row={"count": 10})
            if "UNWIND [label IN labels(n) WHERE label <> $managed_label] AS label" in normalized:
                assert params["managed_label"] == MANAGED_LABEL
                return FakeResult(
                    rows=[
                        {"label": "WorkflowPattern", "count": 14},
                        {"label": "Task", "count": 0},
                        {"label": "ScenarioProfile", "count": 0},
                        {"label": "OutputSchemaPolicy", "count": 0},
                        {"label": "AlgorithmParameterSpec", "count": 0},
                    ]
                )
            if "MATCH (:FusionAgentManaged)-[r]->(:FusionAgentManaged)" in normalized:
                return FakeResult(rows=[])
            executed_statements.append(statement)
            return FakeResult(rows=[])

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
    assert executed_statements == ["MERGE (n:Foo {id: '1'});"] or executed_statements == ["MERGE (n:Foo {id: '1'})"]


def test_resolve_graph_target_falls_back_to_home_database_for_community(monkeypatch) -> None:
    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def single(self):
            return self._rows[0] if self._rows else None

        def __iter__(self):
            return iter(self._rows)

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, statement: str):
            if "CALL dbms.components()" in statement:
                return FakeResult([{"name": "Neo4j Kernel", "versions": ["5.23.0"], "edition": "community"}])
            if "SHOW DATABASES" in statement:
                return FakeResult(
                    [
                        {"name": "system", "home": False, "default": False},
                        {"name": "zmn", "home": True, "default": True},
                    ]
                )
            raise AssertionError(f"Unexpected statement: {statement}")

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

    resolved = resolve_graph_target(
        uri="bolt://localhost:7687",
        user="neo4j",
        password="password",
        database="fusionagent",
    )

    assert resolved["edition"] == "community"
    assert resolved["database_used"] == "zmn"
    assert resolved["isolation_mode"] == "managed-label"
    assert resolved["notes"]
