from __future__ import annotations

from kg.models import AlgorithmParameterSpec
from kg.neo4j_repository import Neo4jKGRepository


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


def test_get_parameter_specs_maps_rows_from_fake_driver() -> None:
    captured: list[tuple[str, object]] = []

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, cypher: str, parameters=None, **kwargs):
            captured.append((cypher, parameters))
            return [
                {
                    "ps": {
                        "specId": "ps.algo.test.threshold",
                        "algoId": "algo.test",
                        "key": "threshold",
                        "label": "Threshold",
                        "paramType": "float",
                        "default": 0.3,
                        "minValue": 0.0,
                        "maxValue": 1.0,
                        "unit": "ratio",
                        "description": "test",
                        "required": True,
                        "choices": [0.1, 0.2, 0.3],
                        "order": 10,
                    },
                    "hs": {"order": 10},
                }
            ]

    class FakeDriver:
        def session(self, database=None):
            return FakeSession()

    repo = Neo4jKGRepository.__new__(Neo4jKGRepository)
    repo._driver = FakeDriver()
    repo.database = None

    specs = repo.get_parameter_specs("algo.test")

    assert specs == [
        AlgorithmParameterSpec(
            spec_id="ps.algo.test.threshold",
            algo_id="algo.test",
            key="threshold",
            label="Threshold",
            param_type="float",
            default=0.3,
            min_value=0.0,
            max_value=1.0,
            unit="ratio",
            description="test",
            required=True,
            choices=[0.1, 0.2, 0.3],
            order=10,
        )
    ]
    assert captured
    assert "AlgorithmParameterSpec" in captured[0][0]
    assert "HAS_PARAMETER_SPEC" in captured[0][0]
    assert captured[0][1] == {"algo_id": "algo.test"}
