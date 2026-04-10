from __future__ import annotations

from kg.models import AlgorithmParameterSpec, DurableLearningRecord
from kg.neo4j_repository import Neo4jKGRepository
from schemas.fusion import JobType


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


def test_record_durable_learning_record_emits_managed_summary_node() -> None:
    captured: list[tuple[str, object]] = []

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, cypher: str, parameters=None, **kwargs):
            captured.append((cypher, parameters))
            return []

    class FakeDriver:
        def session(self, database=None):
            return FakeSession()

    repo = Neo4jKGRepository.__new__(Neo4jKGRepository)
    repo._driver = FakeDriver()
    repo.database = None

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
            metadata={"planning_mode": "task_driven", "profile_source": "default_task"},
            created_at="2026-04-09T00:00:00+00:00",
        )
    )

    assert captured
    assert "DurableLearningRecord" in captured[0][0]
    assert captured[0][1]["record_id"] == "dlr-1"
    assert captured[0][1]["output_data_type"] == "dt.building.fused"
    assert '"planning_mode": "task_driven"' in captured[0][1]["metadata_json"]


def test_list_durable_learning_records_maps_rows_from_fake_driver() -> None:
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
                    "dlr": {
                        "recordId": "dlr-2",
                        "runId": "run-2",
                        "jobType": "road",
                        "triggerType": "disaster_event",
                        "success": False,
                        "disasterType": "flood",
                        "patternId": "wp.flood.road.default",
                        "algorithmId": "algo.fusion.road.v1",
                        "selectedDataSource": "catalog.typhoon.road",
                        "outputDataType": "dt.road.fused",
                        "targetCrs": "EPSG:32643",
                        "repaired": True,
                        "repairCount": 2,
                        "failureReason": "RuntimeError: still failing",
                        "planRevision": 2,
                        "metadataJson": "{\"planning_mode\": \"scenario_driven\", \"profile_source\": \"disaster_type\"}",
                        "createdAt": "2026-04-09T02:00:00+00:00",
                    }
                }
            ]

    class FakeDriver:
        def session(self, database=None):
            return FakeSession()

    repo = Neo4jKGRepository.__new__(Neo4jKGRepository)
    repo._driver = FakeDriver()
    repo.database = None

    rows = repo.list_durable_learning_records(job_type=JobType.road, success=False, limit=5)

    assert rows == [
        DurableLearningRecord(
            record_id="dlr-2",
            run_id="run-2",
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
            metadata={"planning_mode": "scenario_driven", "profile_source": "disaster_type"},
            created_at="2026-04-09T02:00:00+00:00",
        )
    ]
    assert captured
    assert "DurableLearningRecord" in captured[0][0]
    assert captured[0][1] == {"job_type": "road", "success": False, "limit": 5}
