from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import Polygon

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
