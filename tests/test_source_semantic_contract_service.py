from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Polygon

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
    assert contract.height_policy["raster_height_priority_order"] == [
        "raw.google.building_height.raster",
    ]


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


def test_microsoft_road_contract_validates_normalized_fields_not_raw_osm_fields(tmp_path: Path) -> None:
    path = tmp_path / "microsoft-road.gpkg"
    gpd.GeoDataFrame(
        {"WidthMeters": [7.0], "CountryCode": ["VEN"]},
        geometry=[LineString([(0, 0), (1, 0)])],
        crs="EPSG:4326",
    ).to_file(path, driver="GPKG")

    contract = SourceSemanticContractService(kg_repo=_Repo()).build_contract(
        run_id="run-road",
        job_type="road",
        selected_source_id="catalog.typhoon.road",
        component_paths={"raw.microsoft.road": path},
        target_crs="EPSG:32619",
    )

    source = contract.sources["raw.microsoft.road"]
    assert contract.validation["valid"] is True
    assert contract.validation["validated_layer"] == "normalized_algorithm_input"
    assert source.normalization_profile == "normalization.road.microsoft_shapefile.v1"
    assert source.matched_fields["source_feature_id"].resolution == "derived"
    assert source.matched_fields["source_feature_id"].derivation == "provider_artifact_fid"
    assert source.matched_fields["road_class"].resolution == "defaulted"
    assert source.matched_fields["road_class"].default_value == "road"


def test_microsoft_road_contract_fails_when_stable_provider_fid_is_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "microsoft-road.geojson"
    gpd.GeoDataFrame(
        {"WidthMeters": [7.0]},
        geometry=[LineString([(0, 0), (1, 0)])],
        crs="EPSG:4326",
    ).to_file(path, driver="GeoJSON")

    contract = SourceSemanticContractService(kg_repo=_Repo()).build_contract(
        run_id="run-road-no-fid",
        job_type="road",
        selected_source_id="catalog.typhoon.road",
        component_paths={"raw.microsoft.road": path},
        target_crs="EPSG:32619",
    )

    assert contract.validation["valid"] is False
    assert contract.sources["raw.microsoft.road"].matched_fields["source_feature_id"].resolution == "unresolved"


def test_microsoft_road_contract_fails_for_unsupported_geometry(tmp_path: Path) -> None:
    path = tmp_path / "microsoft-road-polygon.gpkg"
    gpd.GeoDataFrame(
        {"WidthMeters": [7.0]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:4326",
    ).to_file(path, driver="GPKG")

    contract = SourceSemanticContractService(kg_repo=_Repo()).build_contract(
        run_id="run-road-polygon",
        job_type="road",
        selected_source_id="catalog.typhoon.road",
        component_paths={"raw.microsoft.road": path},
        target_crs="EPSG:32619",
    )

    assert contract.validation["valid"] is False
    assert any(issue["code"] == "normalization_geometry_unsupported" for issue in contract.validation["issues"])


def test_water_contract_derives_polygon_feature_kind_from_geometry(tmp_path: Path) -> None:
    osm_path = tmp_path / "water.gpkg"
    hydro_path = tmp_path / "hydrolakes.gpkg"
    gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["reservoir"], "name": ["lake"]},
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:4326",
    ).to_file(osm_path, driver="GPKG")
    gpd.GeoDataFrame(
        {"Hylak_id": [2], "Lake_type": [1], "Lake_name": ["reference"]},
        geometry=[Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])],
        crs="EPSG:4326",
    ).to_file(hydro_path, driver="GPKG")

    contract = SourceSemanticContractService(kg_repo=_Repo()).build_contract(
        run_id="run-water",
        job_type="water",
        selected_source_id="catalog.flood.water",
        component_paths={
            "raw.osm.water": osm_path,
            "raw.hydrolakes.water": hydro_path,
        },
        target_crs="EPSG:32619",
    )

    assert contract.validation["valid"] is True
    for source_id in ("raw.osm.water", "raw.hydrolakes.water"):
        matched = contract.sources[source_id].matched_fields["feature_kind"]
        assert matched.resolution == "derived"
        assert matched.derivation == "geometry_type"
        assert matched.default_value == "polygon"


def test_waterways_contract_derives_line_feature_kind_from_geometry(tmp_path: Path) -> None:
    osm_path = tmp_path / "waterways.gpkg"
    hydro_path = tmp_path / "hydrorivers.gpkg"
    gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["stream"], "name": ["stream"]},
        geometry=[LineString([(0, 0), (1, 0)])],
        crs="EPSG:4326",
    ).to_file(osm_path, driver="GPKG")
    gpd.GeoDataFrame(
        {"HYRIV_ID": [2], "ORD_STRA": [1]},
        geometry=[LineString([(0, 0), (0, 1)])],
        crs="EPSG:4326",
    ).to_file(hydro_path, driver="GPKG")

    contract = SourceSemanticContractService(kg_repo=_Repo()).build_contract(
        run_id="run-waterways",
        job_type="waterways",
        selected_source_id="catalog.flood.waterways",
        component_paths={
            "raw.osm.waterways": osm_path,
            "raw.hydrorivers.water": hydro_path,
        },
        target_crs="EPSG:32619",
    )

    assert contract.validation["valid"] is True
    for source_id in ("raw.osm.waterways", "raw.hydrorivers.water"):
        matched = contract.sources[source_id].matched_fields["feature_kind"]
        assert matched.resolution == "derived"
        assert matched.derivation == "geometry_type"
        assert matched.default_value == "line"
