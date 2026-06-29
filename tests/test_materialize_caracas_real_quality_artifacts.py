from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Point, box

from scripts.materialize_caracas_real_quality_artifacts import (
    materialize_caracas_real_quality_artifacts,
)
from scripts.run_fusion_quality_benchmark import run_manifest


def _write(frame: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".gpkg":
        frame.to_file(path, driver="GPKG")
    else:
        frame.to_file(path)


def test_materialize_caracas_real_quality_artifacts_can_feed_quality_benchmark(tmp_path: Path) -> None:
    source_root = tmp_path / "caracas"
    osm_root = source_root / "osm"
    manifest = tmp_path / "caracas-manifest.json"
    output_dir = tmp_path / "caracas-out"

    _write(
        gpd.GeoDataFrame({"id": [1]}, geometry=[box(0, 0, 10, 10)], crs="EPSG:3857"),
        source_root / "Microsoft_capital_district.gpkg",
    )
    _write(
        gpd.GeoDataFrame({"id": [2]}, geometry=[box(0.5, 0.5, 10.5, 10.5)], crs="EPSG:3857"),
        source_root / "googlebuildingv3.gpkg",
    )
    _write(
        gpd.GeoDataFrame({"id": [3]}, geometry=[box(40, 40, 50, 50)], crs="EPSG:3857"),
        osm_root / "buildings.shp",
    )
    _write(
        gpd.GeoDataFrame({"id": [1], "fclass": ["primary"]}, geometry=[LineString([(0, 0), (10, 0)])], crs="EPSG:3857"),
        osm_root / "roads.shp",
    )
    _write(
        gpd.GeoDataFrame({"id": [2], "fclass": ["road"]}, geometry=[LineString([(0, 30), (10, 30)])], crs="EPSG:3857"),
        source_root / "microsoft_roads_capital.gpkg",
    )
    _write(
        gpd.GeoDataFrame({"id": [1], "fclass": ["river"]}, geometry=[LineString([(0, 0), (10, 0)])], crs="EPSG:3857"),
        osm_root / "waterways.shp",
    )
    _write(
        gpd.GeoDataFrame({"id": [2], "waterway": ["river"]}, geometry=[LineString([(0, 30), (10, 30)])], crs="EPSG:3857"),
        source_root / "hydrorivers_capital.gpkg",
    )
    _write(
        gpd.GeoDataFrame({"id": [1]}, geometry=[box(100, 100, 150, 150)], crs="EPSG:3857"),
        osm_root / "water.shp",
    )
    _write(
        gpd.GeoDataFrame({"name": ["Clinic"]}, geometry=[Point(0, 0)], crs="EPSG:3857"),
        source_root / "geonames_capital.gpkg",
    )
    _write(
        gpd.GeoDataFrame({"name": ["Clinic"]}, geometry=[Point(1, 0)], crs="EPSG:3857"),
        osm_root / "poi.shp",
    )

    result = materialize_caracas_real_quality_artifacts(
        source_root=source_root,
        output_dir=output_dir,
        manifest_path=manifest,
        target_crs="EPSG:3857",
    )
    payload = json.loads(manifest.read_text(encoding="utf-8"))

    assert result["summary"]["artifact_count"] == 5
    assert payload["manifest_id"] == "freeze-b-caracas-real-v1"
    assert {case["case_id"] for case in payload["cases"]} == {
        "case.building.real.caracas",
        "case.road.real.caracas",
        "case.waterways.real.caracas",
        "case.water_polygon.real.caracas.single_source_sanity",
        "case.poi.real.caracas",
    }
    assert all(Path(case["precomputed_artifact_path"]).exists() for case in payload["cases"])
    assert "not a multi-source fusion superiority claim" in json.dumps(payload, ensure_ascii=False)

    summary = run_manifest(manifest, output_dir=tmp_path / "quality-out")

    assert summary["manifest_id"] == "freeze-b-caracas-real-v1"
    assert summary["result_count"] == 5
    assert summary["quality_claim_case_count"] == 5
    assert summary["accepted_quality_claim_count"] == 5
    assert summary["accepted_non_smoke_claim_count"] == 5
