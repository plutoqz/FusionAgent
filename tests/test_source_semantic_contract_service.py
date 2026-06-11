from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

from kg.source_catalog import build_data_sources
from services.source_semantic_contract_service import SourceSemanticContract, SourceSemanticContractService


class _Repo:
    def list_data_sources(self):
        return build_data_sources()


def _write_building(path: Path) -> Path:
    gdf = gpd.GeoDataFrame(
        {
            "id": ["ms-1"],
            "HEIGHT": [12.5],
            "Name": ["clinic"],
        },
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:4326",
    )
    gdf.to_file(path, driver="GPKG")
    return path


def test_semantic_contract_matches_actual_height_field(tmp_path: Path) -> None:
    source_path = _write_building(tmp_path / "microsoft.gpkg")
    service = SourceSemanticContractService(kg_repo=_Repo())

    contract = service.build_contract(
        run_id="run-1",
        job_type="building",
        selected_source_id="catalog.earthquake.building",
        component_paths={"raw.microsoft.building": source_path},
        target_crs="EPSG:4326",
    )

    ms = contract.sources["raw.microsoft.building"]
    assert ms.field_mapping_profile == "fields.building.microsoft"
    assert ms.matched_fields["height_m"].matched_field == "HEIGHT"
    assert ms.height_semantics == "estimated_height"
    assert contract.height_policy["vector_height_fields"]["raw.microsoft.building"] == "HEIGHT"


def test_semantic_contract_marks_required_missing_fields(tmp_path: Path) -> None:
    gdf = gpd.GeoDataFrame(
        {"name": ["nameless-id"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:4326",
    )
    path = tmp_path / "bad.gpkg"
    gdf.to_file(path, driver="GPKG")
    service = SourceSemanticContractService(kg_repo=_Repo())

    contract = service.build_contract(
        run_id="run-2",
        job_type="building",
        selected_source_id="catalog.earthquake.building",
        component_paths={"raw.microsoft.building": path},
        target_crs="EPSG:4326",
    )

    issues = contract.validation["issues"]
    assert {
        "source_id": "raw.microsoft.building",
        "canonical_field": "source_feature_id",
        "code": "required_field_unmatched",
    } in issues


def test_semantic_contract_to_dict_includes_top_level_metadata() -> None:
    contract = SourceSemanticContract(
        run_id="run-1",
        job_type="building",
        selected_source_id="catalog.earthquake.building",
        target_crs="EPSG:4326",
        component_source_ids=["raw.google.building", "raw.osm.building"],
        sources={},
        metadata={"country_name": "Nepal", "aoi_size_bucket": "small"},
    )

    payload = contract.to_dict()

    assert payload["metadata"] == {"country_name": "Nepal", "aoi_size_bucket": "small"}
