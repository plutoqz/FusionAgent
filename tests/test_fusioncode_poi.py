from __future__ import annotations

import geopandas as gpd
import pytest
from shapely.geometry import Point

from adapters.fusioncode_poi_adapter import DEFAULT_POI_SOURCE_PRIORITY_ORDER
from adapters.fusioncode_poi_adapter import run_poi_geohash_neighbor_match
from agent.executor import ExecutionContext
from fusion_algorithms.contracts import ConflictDetectionParams, PoiFusionParams
from fusion_algorithms.poi_fusion import build_geohash_candidates, match_poi_neighbors
from fusion_algorithms.quality import detect_spatial_conflicts
from schemas.fusion import JobType


def _write_points(path, *, source_id: str):
    frame = gpd.GeoDataFrame(
        {
            "source_id": [source_id],
            "name": [source_id],
            "category": ["poi"],
        },
        geometry=[Point(0, 0)],
        crs="EPSG:4326",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path, driver="GPKG")
    return path


def test_poi_geohash_candidates_match_same_hash() -> None:
    base = gpd.GeoDataFrame({"GeoHash": ["abc"], "name": ["Clinic"]}, geometry=[Point(0, 0)], crs="EPSG:4326")
    target = gpd.GeoDataFrame({"GeoHash": ["abc"], "name": ["Clinic"]}, geometry=[Point(0, 0)], crs="EPSG:4326")
    candidates = build_geohash_candidates(base, target, PoiFusionParams(name_similarity_threshold=0.8))
    assert len(candidates) == 1
    assert candidates.iloc[0]["name_score"] == 1.0


def test_poi_distance_fallback_when_geohash_missing() -> None:
    base = gpd.GeoDataFrame({"name": ["Clinic"]}, geometry=[Point(0, 0)], crs="EPSG:3857")
    target = gpd.GeoDataFrame({"name": ["Clinic"]}, geometry=[Point(1, 0)], crs="EPSG:3857")
    matches = match_poi_neighbors(base, target, PoiFusionParams(duplicate_distance_m=5.0))
    assert len(matches) == 1


def test_conflict_detection_reports_polygon_overlap() -> None:
    gdf = gpd.GeoDataFrame({"id": [1, 2]}, geometry=[Point(0, 0).buffer(2), Point(1, 0).buffer(2)], crs="EPSG:3857")
    conflicts = detect_spatial_conflicts(gdf, ConflictDetectionParams(overlap_area_min=0.1))
    assert len(conflicts) == 1
    assert conflicts[0]["overlap_area"] > 0.1


def test_poi_adapter_preserves_gng_google_osm_order(tmp_path, monkeypatch) -> None:
    paths = {
        "OSM": _write_points(tmp_path / "osm.gpkg", source_id="raw.osm.poi"),
        "GOOGLE": _write_points(tmp_path / "google.gpkg", source_id="raw.google.poi"),
        "GNG": _write_points(tmp_path / "gns.gpkg", source_id="raw.gns.poi"),
    }
    captured = {}

    def fake_run(sources, params=None):
        captured["keys"] = list(sources)
        captured["params_order"] = tuple(params.source_priority_order)
        return next(iter(sources.values()))

    monkeypatch.setattr("adapters.fusioncode_poi_adapter.run_poi_geohash_priority_fusion", fake_run)

    context = ExecutionContext(
        run_id="test-run",
        job_type=JobType.poi,
        osm_shp=tmp_path / "unused_osm.shp",
        ref_shp=tmp_path / "unused_ref.shp",
        output_dir=tmp_path / "out",
        target_crs="EPSG:4326",
        named_vectors=paths,
    )
    run_poi_geohash_neighbor_match(context)

    assert captured["keys"] == ["GNG", "GOOGLE", "OSM"]
    assert captured["params_order"][:3] == ("GNG", "GOOGLE", "OSM")


def test_poi_adapter_default_priority_includes_rh_and_keeps_contract_consistent(tmp_path, monkeypatch) -> None:
    paths = {
        "RH": _write_points(tmp_path / "rh.gpkg", source_id="raw.rh.poi"),
        "OSM": _write_points(tmp_path / "osm.gpkg", source_id="raw.osm.poi"),
        "GOOGLE": _write_points(tmp_path / "google.gpkg", source_id="raw.google.poi"),
        "GNG": _write_points(tmp_path / "gns.gpkg", source_id="raw.gns.poi"),
    }
    captured = {}

    def fake_run(sources, params=None):
        captured["keys"] = list(sources)
        captured["params_order"] = tuple(params.source_priority_order)
        return next(iter(sources.values()))

    monkeypatch.setattr("adapters.fusioncode_poi_adapter.run_poi_geohash_priority_fusion", fake_run)

    context = ExecutionContext(
        run_id="test-run",
        job_type=JobType.poi,
        osm_shp=tmp_path / "unused_osm.shp",
        ref_shp=tmp_path / "unused_ref.shp",
        output_dir=tmp_path / "out",
        target_crs="EPSG:4326",
        named_vectors=paths,
    )
    run_poi_geohash_neighbor_match(context)

    assert DEFAULT_POI_SOURCE_PRIORITY_ORDER == PoiFusionParams().source_priority_order
    assert captured["keys"] == ["GNG", "GOOGLE", "OSM", "RH"]
    assert captured["params_order"] == ("GNG", "GOOGLE", "OSM", "RH")
