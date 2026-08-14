from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Polygon

from kg.source_catalog import build_data_sources
from services.source_semantic_contract_service import SourceSemanticContractService
from services.track_b_source_normalization import normalize_track_b_source_frame


class _Repo:
    def list_data_sources(self):
        return build_data_sources()


def test_normalization_uses_semantic_contract_matched_height_field(tmp_path: Path) -> None:
    path = tmp_path / "ms.gpkg"
    frame = gpd.GeoDataFrame(
        {
            "quadkey": ["q1"],
            "HEIGHT": [14.0],
            "Name": ["school"],
        },
        geometry=[Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")
    contract = SourceSemanticContractService(kg_repo=_Repo()).build_contract(
        run_id="run-1",
        job_type="building",
        selected_source_id="catalog.earthquake.building",
        component_paths={"raw.microsoft.building": path},
        target_crs="EPSG:4326",
    )

    normalized = normalize_track_b_source_frame(
        "raw.microsoft.building",
        frame,
        target_crs="EPSG:4326",
        source_semantics=contract.sources["raw.microsoft.building"],
    )

    assert list(normalized["source_feature_id"]) == ["q1"]
    assert float(normalized.loc[0, "height_m"]) == 14.0
    assert normalized.loc[0, "field_mapping_profile"] == "fields.building.microsoft"


def test_microsoft_road_normalization_materializes_declared_canonical_fields(tmp_path: Path) -> None:
    path = tmp_path / "ms-road.gpkg"
    frame = gpd.GeoDataFrame(
        {"WidthMeters": [7.0]},
        geometry=[LineString([(0, 0), (1, 0)])],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")
    contract = SourceSemanticContractService(kg_repo=_Repo()).build_contract(
        run_id="run-road",
        job_type="road",
        selected_source_id="catalog.typhoon.road",
        component_paths={"raw.microsoft.road": path},
        target_crs="EPSG:4326",
    )

    normalized = normalize_track_b_source_frame(
        "raw.microsoft.road",
        frame,
        target_crs="EPSG:4326",
        source_semantics=contract.sources["raw.microsoft.road"],
    )

    assert normalized.loc[0, "source_feature_id"] == "0"
    assert normalized.loc[0, "FID_1"] == 0
    assert normalized.loc[0, "road_class"] == "road"
    assert normalized.loc[0, "source_feature_id_provenance"] == "provider_artifact_fid"
    assert normalized.loc[0, "road_class_provenance"] == "declared_default:road"


def test_microsoft_road_normalization_rejects_unstable_fids() -> None:
    frame = gpd.GeoDataFrame(
        {"WidthMeters": [7.0, 8.0]},
        geometry=[LineString([(0, 0), (1, 0)]), LineString([(0, 1), (1, 1)])],
        crs="EPSG:4326",
        index=[4, 4],
    )

    with pytest.raises(ValueError, match="SOURCE_NORMALIZATION_STABLE_FID_UNAVAILABLE"):
        normalize_track_b_source_frame(
            "raw.microsoft.road",
            frame,
            target_crs="EPSG:4326",
        )


def test_microsoft_road_normalization_rejects_missing_crs() -> None:
    frame = gpd.GeoDataFrame(
        {"WidthMeters": [7.0]},
        geometry=[LineString([(0, 0), (1, 0)])],
    )

    with pytest.raises(ValueError, match="SOURCE_NORMALIZATION_CRS_UNRESOLVED"):
        normalize_track_b_source_frame(
            "raw.microsoft.road",
            frame,
            target_crs="EPSG:32619",
        )
