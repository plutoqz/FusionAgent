from __future__ import annotations

import inspect

import geopandas as gpd
from shapely.geometry import box

from fusion_algorithms import building_matching_v8
from fusion_algorithms.contracts import BuildingMatchParams


def _gdf(name: str) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"name": [name]}, geometry=[box(0, 0, 1, 1)], crs="EPSG:3857")


def test_decomposed_v8_runtime_does_not_call_full_pipeline() -> None:
    source = inspect.getsource(building_matching_v8)
    assert "run_full_pipeline(" not in source


def test_decomposed_v8_runtime_exposes_primitive_steps() -> None:
    required = [
        "normalize_building_sources",
        "build_v8_candidate_graph",
        "solve_v8_components",
        "build_cascade_fusion_rows",
        "resolve_residual_priority_conflicts",
        "run_pairwise_v8_fusion",
        "run_cascaded_multi_source_fusion",
    ]
    missing = [name for name in required if not hasattr(building_matching_v8, name)]
    assert missing == []


def test_cascaded_multi_source_fusion_respects_source_order(monkeypatch) -> None:
    calls = []

    def fake_pairwise(base_gdf, target_gdf, roads, params, *, base_name, target_name):
        calls.append((base_name, target_name))
        return _gdf(f"{base_name}_{target_name}")

    monkeypatch.setattr(building_matching_v8, "run_pairwise_v8_fusion", fake_pairwise)
    result = building_matching_v8.run_cascaded_multi_source_fusion(
        {"MS": _gdf("ms"), "GG": _gdf("gg"), "OSM": _gdf("osm")},
        roads=None,
        params=BuildingMatchParams(source_priority_order=("MS", "GG", "OSM")),
    )
    assert calls == [("MS", "GG"), ("FUSED_MS_GG", "OSM")]
    assert len(result) == 1
