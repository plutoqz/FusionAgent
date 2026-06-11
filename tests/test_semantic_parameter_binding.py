from __future__ import annotations

from agent.semantic_parameter_binding import bind_source_semantic_parameters
from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import WorkflowPlan
from services.source_semantic_contract_service import SourceSemanticContract


def _plan(job_type: str, algorithm_id: str) -> WorkflowPlan:
    return WorkflowPlan.model_validate(
        {
            "workflow_id": "wf_semantic",
            "trigger": {"type": "user_query", "content": job_type},
            "tasks": [
                {
                    "step": 1,
                    "name": "fusion",
                    "description": "fusion",
                    "algorithm_id": algorithm_id,
                    "input": {
                        "data_type_id": f"dt.{job_type}.bundle",
                        "data_source_id": f"catalog.generic.{job_type}",
                        "parameters": {},
                    },
                    "output": {"data_type_id": f"dt.{job_type}.fused"},
                }
            ],
            "expected_output": f"dt.{job_type}.fused",
        }
    )


def _contract_with_metadata(*, component_source_ids: list[str], metadata: dict) -> object:
    class _Contract:
        run_id = "run-1"
        job_type = "building"
        selected_source_id = "catalog.earthquake.building"
        target_crs = "EPSG:4326"
        sources = {}
        height_policy = {}
        parameter_hints = {}
        validation = {"valid": True, "issues": []}

        def __init__(self) -> None:
            self.component_source_ids = component_source_ids
            self.metadata = metadata

    return _Contract()


def test_semantic_binding_adds_building_height_and_priority_parameters() -> None:
    contract = SourceSemanticContract(
        run_id="run-1",
        job_type="building",
        selected_source_id="catalog.earthquake.building",
        target_crs="EPSG:4326",
        component_source_ids=["raw.microsoft.building", "raw.osm.building"],
        sources={},
        height_policy={
            "height_output_field": "height_raster",
            "canonical_height_field": "height",
            "positive_only": True,
            "vector_height_fields": {"raw.microsoft.building": "HEIGHT"},
        },
        parameter_hints={"source_priority_order": ["MS", "OSM"]},
        validation={"valid": True, "issues": []},
    )
    plan = _plan("building", "algo.fusion.building.v1")

    bound = bind_source_semantic_parameters(plan, contract)

    params = bound.tasks[0].input.parameters
    assert params["source_semantic_contract_path"] == "source_semantic_contract.json"
    assert params["height_output_field"] == "height_raster"
    assert params["canonical_height_field"] == "height"
    assert params["positive_only"] is True
    assert params["source_priority_order"] == ["MS", "OSM"]


def test_semantic_binding_adds_poi_geohash_precision() -> None:
    contract = SourceSemanticContract(
        run_id="run-1",
        job_type="poi",
        selected_source_id="catalog.generic.poi",
        target_crs="EPSG:4326",
        component_source_ids=["raw.osm.poi", "raw.gns.poi"],
        sources={},
        parameter_hints={"geohash_precision": 8},
        validation={"valid": True, "issues": []},
    )
    plan = _plan("poi", "algo.fusion.poi.v1")

    bound = bind_source_semantic_parameters(plan, contract)

    assert bound.tasks[0].input.parameters["geohash_precision"] == 8


class _FakeSpec:
    def __init__(self, key: str) -> None:
        self.key = key


class _FakeKG:
    def __init__(self, keys: set[str]) -> None:
        self.keys = keys

    def get_parameter_specs(self, _algorithm_id: str):
        return [_FakeSpec(key) for key in sorted(self.keys)]


def test_semantic_binding_skips_parameters_not_supported_by_algorithm_specs() -> None:
    contract = SourceSemanticContract(
        run_id="run-1",
        job_type="building",
        selected_source_id="catalog.earthquake.building",
        target_crs="EPSG:4326",
        component_source_ids=["raw.microsoft.building", "raw.osm.building"],
        sources={},
        height_policy={
            "height_output_field": "height_raster",
            "canonical_height_field": "height",
            "positive_only": True,
        },
        parameter_hints={"source_priority_order": ["MS", "OSM"]},
        validation={"valid": True, "issues": []},
    )
    plan = _plan("building", "algo.fusion.road.v1")

    bound = bind_source_semantic_parameters(plan, contract, kg_repo=_FakeKG({"source_semantic_contract_path"}))

    params = bound.tasks[0].input.parameters
    assert params == {"source_semantic_contract_path": "source_semantic_contract.json"}


def test_semantic_parameter_binding_uses_conditional_parameter_defaults() -> None:
    plan = _plan("building", "algo.fusion.building.v1")
    contract = _contract_with_metadata(
        component_source_ids=["raw.google.building", "raw.osm.building"],
        metadata={"country_name": "Nepal"},
    )

    bound = bind_source_semantic_parameters(plan, contract, kg_repo=InMemoryKGRepository())

    params = bound.tasks[0].input.parameters
    assert params["match_similarity_threshold"] == 0.75
    assert params["parameter_provenance"]["match_similarity_threshold"]["source"] == "manual_seed"


def test_semantic_parameter_binding_keeps_explicit_parameter_over_conditional_default() -> None:
    plan = _plan("building", "algo.fusion.building.v1")
    plan.tasks[0].input.parameters["match_similarity_threshold"] = 0.9
    contract = _contract_with_metadata(
        component_source_ids=["raw.google.building", "raw.osm.building"],
        metadata={"country_name": "Nepal"},
    )

    bound = bind_source_semantic_parameters(plan, contract, kg_repo=InMemoryKGRepository())

    params = bound.tasks[0].input.parameters
    assert params["match_similarity_threshold"] == 0.9
    assert params["parameter_provenance"]["match_similarity_threshold"]["source"] == "manual_seed"
