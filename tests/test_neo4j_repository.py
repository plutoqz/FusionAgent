from __future__ import annotations

from kg.models import AlgorithmNode, AlgorithmParameterSpec, DataSourceNode, DurableLearningRecord, PatternStep, WorkflowPatternNode
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


def test_list_methods_map_rows_from_fake_driver() -> None:
    captured: list[tuple[str, object]] = []

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, cypher: str, parameters=None, **kwargs):
            captured.append((cypher, parameters))
            if "MATCH (a:Algorithm" in cypher:
                return [
                    {
                        "algo": {
                            "algoId": "algo.fusion.building.v1",
                            "algoName": "Building Fusion Legacy",
                            "inputTypes": ["dt.building.bundle"],
                            "outputType": "dt.building.fused",
                            "taskType": "building_fusion",
                            "toolRef": "adapters.building_adapter:run_building_fusion",
                            "successRate": 0.92,
                            "accuracyScore": 0.89,
                            "stabilityScore": 0.74,
                            "usageMode": "throughput",
                            "metadataJson": "{\"selection_profile\": \"primary\"}",
                        },
                        "alternatives": ["algo.fusion.building.safe"],
                    }
                ]
            if "MATCH (wp:WorkflowPattern" in cypher:
                return [
                    {
                        "wp": {
                            "patternId": "wp.flood.building.default",
                            "patternName": "Flood Building Default",
                            "jobType": "building",
                            "disasterTypes": ["flood"],
                            "successRate": 0.91,
                            "metadataJson": "{\"entry_mode\": \"scenario_driven\"}",
                        },
                        "steps": [
                            {
                                "order": 1,
                                "name": "building_fusion",
                                "algorithmId": "algo.fusion.building.v1",
                                "inputDataType": "dt.building.bundle",
                                "outputDataType": "dt.building.fused",
                                "dataSourceId": "upload.bundle",
                                "dependsOn": [],
                                "isOptional": False,
                            }
                        ],
                    }
                ]
            if "MATCH (ds:DataSource" in cypher:
                return [
                    {
                        "ds": {
                            "sourceId": "catalog.flood.building",
                            "sourceName": "Flood Building Bundle",
                            "supportedTypes": ["dt.building.bundle"],
                            "disasterTypes": ["flood"],
                            "qualityScore": 0.88,
                            "sourceKind": "catalog",
                            "qualityTier": "curated",
                            "freshnessCategory": "event_snapshot",
                            "freshnessHours": 96,
                            "freshnessScore": 0.71,
                            "supportedJobTypes": ["building"],
                            "supportedGeometryTypes": ["polygon"],
                            "metadataJson": "{\"bundle_strategy\": \"osm_ref_pair\"}",
                        }
                    }
                ]
            return []

    class FakeDriver:
        def session(self, database=None):
            return FakeSession()

    repo = Neo4jKGRepository.__new__(Neo4jKGRepository)
    repo._driver = FakeDriver()
    repo.database = None

    assert repo.list_algorithms() == [
        AlgorithmNode(
            algo_id="algo.fusion.building.v1",
            algo_name="Building Fusion Legacy",
            input_types=["dt.building.bundle"],
            output_type="dt.building.fused",
            task_type="building_fusion",
            tool_ref="adapters.building_adapter:run_building_fusion",
            success_rate=0.92,
            accuracy_score=0.89,
            stability_score=0.74,
            usage_mode="throughput",
            metadata={"selection_profile": "primary"},
            alternatives=["algo.fusion.building.safe"],
        )
    ]
    assert repo.list_workflow_patterns() == [
        WorkflowPatternNode(
            pattern_id="wp.flood.building.default",
            pattern_name="Flood Building Default",
            job_type=JobType.building,
            disaster_types=["flood"],
            steps=[
                PatternStep(
                    order=1,
                    name="building_fusion",
                    algorithm_id="algo.fusion.building.v1",
                    input_data_type="dt.building.bundle",
                    output_data_type="dt.building.fused",
                    data_source_id="upload.bundle",
                    depends_on=[],
                    is_optional=False,
                )
            ],
            success_rate=0.91,
            metadata={"entry_mode": "scenario_driven"},
        )
    ]
    assert repo.list_data_sources() == [
        DataSourceNode(
            source_id="catalog.flood.building",
            source_name="Flood Building Bundle",
            supported_types=["dt.building.bundle"],
            disaster_types=["flood"],
            quality_score=0.88,
            source_kind="catalog",
            quality_tier="curated",
            freshness_category="event_snapshot",
            freshness_hours=96,
            freshness_score=0.71,
            supported_job_types=["building"],
            supported_geometry_types=["polygon"],
            metadata={"bundle_strategy": "osm_ref_pair"},
        )
    ]
    assert len(captured) == 3
    assert "MATCH (a:Algorithm" in captured[0][0]
    assert "MATCH (wp:WorkflowPattern" in captured[1][0]
    assert "MATCH (ds:DataSource" in captured[2][0]


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


def test_build_context_includes_transform_algorithms_and_decomposed_specs_from_fake_driver() -> None:
    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def run(self, cypher: str, parameters=None, **kwargs):
            if "MATCH (wp:WorkflowPattern" in cypher and "LIMIT $limit" in cypher:
                return [
                    {
                        "wp": {
                            "patternId": "wp.building.drs4br.decomposed.v1",
                            "patternName": "FusionCode DRS4BR Decomposed Building Fusion",
                            "jobType": "building",
                            "disasterTypes": ["generic"],
                            "successRate": 0.84,
                            "metadataJson": "{\"algorithm_family\": \"fusioncode_decomposed\"}",
                        },
                        "steps": [
                            {
                                "order": 1,
                                "name": "source_normalize",
                                "algorithmId": "algo.preprocess.building.source_normalize.v1",
                                "inputDataType": "dt.building.source_set",
                                "outputDataType": "dt.building.normalized_set",
                                "dataSourceId": "upload.bundle",
                                "dependsOn": [],
                                "isOptional": False,
                            },
                            {
                                "order": 2,
                                "name": "v8_candidate_graph",
                                "algorithmId": "algo.match.building.v8_candidate_graph.v1",
                                "inputDataType": "dt.building.normalized_set",
                                "outputDataType": "dt.building.match_candidate_graph",
                                "dataSourceId": "upload.bundle",
                                "dependsOn": [1],
                                "isOptional": False,
                            },
                        ],
                    }
                ]
            if "MATCH (a:Algorithm" in cypher and "{algoId: $algo_id}" in cypher:
                algo_id = parameters["algo_id"]
                algorithms = {
                    "algo.preprocess.building.source_normalize.v1": {
                        "algoId": "algo.preprocess.building.source_normalize.v1",
                        "algoName": "Source Normalize",
                        "inputTypes": ["dt.building.source_set"],
                        "outputType": "dt.building.normalized_set",
                        "taskType": "preprocess",
                        "toolRef": "builtin:normalize",
                        "successRate": 0.8,
                        "metadataJson": "{}",
                    },
                    "algo.match.building.v8_candidate_graph.v1": {
                        "algoId": "algo.match.building.v8_candidate_graph.v1",
                        "algoName": "V8 Candidate Graph",
                        "inputTypes": ["dt.building.normalized_set"],
                        "outputType": "dt.building.match_candidate_graph",
                        "taskType": "match",
                        "toolRef": "builtin:v8_graph",
                        "successRate": 0.8,
                        "metadataJson": "{}",
                    },
                    "algo.transform.dt.raw.vector_to_dt.building.source_set": {
                        "algoId": "algo.transform.dt.raw.vector_to_dt.building.source_set",
                        "algoName": "Raw To Building Source Set",
                        "inputTypes": ["dt.raw.vector"],
                        "outputType": "dt.building.source_set",
                        "taskType": "transform",
                        "toolRef": "builtin:transform",
                        "successRate": 0.8,
                        "metadataJson": "{}",
                    },
                }
                algo = algorithms.get(algo_id)
                if algo is None:
                    return []
                return [{"algo": algo, "alternatives": []}]
            if "MATCH (algo:Algorithm" in cypher and "HAS_PARAMETER_SPEC" in cypher:
                return [
                    {
                        "ps": {
                            "specId": "ps.algo.match.building.v8_component_solver.v1.edge_min_score",
                            "algoId": "algo.match.building.v8_component_solver.v1",
                            "key": "edge_min_score",
                            "label": "Edge Min Score",
                            "paramType": "float",
                            "default": 0.5,
                            "minValue": 0.0,
                            "maxValue": 1.0,
                            "description": "threshold",
                            "required": False,
                            "optimizationTags": ["precision"],
                            "order": 1,
                        },
                        "hs": {"order": 1},
                    }
                ] if parameters["algo_id"] == "algo.match.building.v8_component_solver.v1" else []
            if "MATCH (dt:DataType" in cypher:
                return [
                    {"dt": {"typeId": "dt.raw.vector", "theme": "generic", "geometryType": "mixed", "description": "raw"}},
                    {"dt": {"typeId": "dt.building.source_set", "theme": "building", "geometryType": "mixed", "description": "source set"}},
                    {"dt": {"typeId": "dt.building.normalized_set", "theme": "building", "geometryType": "polygon", "description": "normalized"}},
                    {"dt": {"typeId": "dt.building.match_candidate_graph", "theme": "building", "geometryType": "graph", "description": "graph"}},
                ]
            if "MATCH (ds:DataSource" in cypher:
                return [
                    {
                        "ds": {
                            "sourceId": "upload.bundle",
                            "sourceName": "Upload Bundle",
                            "supportedTypes": ["dt.building.source_set"],
                            "disasterTypes": ["generic"],
                            "qualityScore": 1.0,
                            "sourceKind": "upload",
                            "supportedJobTypes": ["building"],
                            "supportedGeometryTypes": ["mixed"],
                            "metadataJson": "{}",
                        }
                    }
                ]
            if "MATCH (osp:OutputSchemaPolicy" in cypher:
                return []
            if "MATCH (task:Task" in cypher:
                return []
            if "MATCH (profile:ScenarioProfile" in cypher:
                return []
            if "MATCH (dlr:DurableLearningRecord" in cypher:
                return []
            return []

    class FakeDriver:
        def session(self, database=None):
            return FakeSession()

    repo = Neo4jKGRepository.__new__(Neo4jKGRepository)
    repo._driver = FakeDriver()
    repo.database = None

    context = repo.build_context(job_type=JobType.building, disaster_type="generic")

    assert any(pattern.pattern_id == "wp.building.drs4br.decomposed.v1" for pattern in context.patterns)
    assert "algo.match.building.v8_candidate_graph.v1" in context.algorithms
