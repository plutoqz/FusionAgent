from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point, Polygon, box

import services.domain_fusion_runners as domain_runners
from services.large_area_runtime_service import LargeAreaRuntimeService, LargeAreaSlice
from services.tile_partition_service import TileManifest, TileSpec


def _manifest() -> TileManifest:
    return TileManifest(
        bbox=(0.0, 0.0, 2.0, 1.0),
        bbox_crs="EPSG:3857",
        working_crs="EPSG:3857",
        tile_width_m=1.0,
        tile_height_m=1.0,
        overlap_m=0.2,
        tiles=[
            TileSpec(
                "tile_000_000",
                (0.0, 0.0, 1.0, 1.0),
                (-0.2, -0.2, 1.2, 1.2),
                (0.0, 0.0, 1.0, 1.0),
                (-0.2, -0.2, 1.2, 1.2),
                0,
                0,
            ),
            TileSpec(
                "tile_000_001",
                (1.0, 0.0, 2.0, 1.0),
                (0.8, -0.2, 2.2, 1.2),
                (1.0, 0.0, 2.0, 1.0),
                (0.8, -0.2, 2.2, 1.2),
                0,
                1,
            ),
        ],
    )


def _write(path: Path, frame: gpd.GeoDataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path, driver="GPKG")
    return path


def test_large_area_runtime_stitches_owner_bbox_without_overlap_duplicates(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "source.gpkg",
        gpd.GeoDataFrame(
            {"source_id": ["raw.test", "raw.test"]},
            geometry=[Point(0.5, 0.5), Point(1.5, 0.5)],
            crs="EPSG:3857",
        ),
    )

    def runner(tile, sources, output_dir, target_crs, parameters):
        del sources, parameters
        frame = gpd.GeoDataFrame(
            {"source_id": ["raw.test", "raw.test"], "canonical_id": ["a", "b"]},
            geometry=[Point(0.5, 0.5), Point(1.5, 0.5)],
            crs=target_crs,
        )
        path = output_dir / "fused.gpkg"
        frame.to_file(path, driver="GPKG")
        return path, {"algorithm_id": "algo.test.points", "tile_id": tile.tile_id}

    result = LargeAreaRuntimeService(max_workers=1).run(
        run_id="run-large-area",
        job_type="poi",
        tile_manifest=_manifest(),
        slices=[LargeAreaSlice(name="poi", geometry_family="point", sources={"raw.test": source}, runner=runner)],
        output_dir=tmp_path / "out",
        target_crs="EPSG:3857",
        parameters={},
    )

    fused = gpd.read_file(result.output_path)
    evidence = json.loads((tmp_path / "out" / "stitched_artifact.json").read_text(encoding="utf-8"))

    assert len(fused) == 2
    assert set(fused["canonical_id"]) == {"a", "b"}
    assert result.tile_count == 2
    assert evidence["tile_count"] == 2
    assert evidence["stitched_feature_count"] == 2


def test_large_area_runtime_clips_final_polygon_output_to_boundary(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "water.gpkg",
        gpd.GeoDataFrame({"source_id": ["raw.water"]}, geometry=[box(-1.0, -1.0, 2.0, 2.0)], crs="EPSG:3857"),
    )
    clip_boundary = gpd.GeoDataFrame({"name": ["clip"]}, geometry=[box(0.0, 0.0, 1.0, 1.0)], crs="EPSG:3857")

    def runner(tile, sources, output_dir, target_crs, parameters):
        del tile, sources, parameters
        path = output_dir / "fused.gpkg"
        gpd.GeoDataFrame(
            {"source_id": ["raw.water"], "feature_kind": ["polygon"]},
            geometry=[box(-1.0, -1.0, 2.0, 2.0)],
            crs=target_crs,
        ).to_file(path, driver="GPKG")
        return path, {"algorithm_id": "algo.test.water"}

    result = LargeAreaRuntimeService(max_workers=1).run(
        run_id="run-water",
        job_type="water",
        tile_manifest=_manifest(),
        slices=[
            LargeAreaSlice(
                name="water_polygon",
                geometry_family="polygon",
                sources={"raw.water": source},
                runner=runner,
            )
        ],
        output_dir=tmp_path / "out-water",
        target_crs="EPSG:3857",
        parameters={},
        clip_boundary=clip_boundary,
    )

    fused = gpd.read_file(result.output_path)
    assert fused.geometry.iloc[0].within(box(0.0, 0.0, 1.0, 1.0)) or fused.geometry.iloc[0].equals(
        box(0.0, 0.0, 1.0, 1.0)
    )


def test_large_area_runtime_preserves_complete_cross_tile_line_geometry(tmp_path: Path) -> None:
    source = _write(
        tmp_path / "roads.gpkg",
        gpd.GeoDataFrame(
            {"source_id": ["raw.road"], "source_feature_id": ["road-1"]},
            geometry=[LineString([(0.0, 0.5), (2.0, 0.5)])],
            crs="EPSG:3857",
        ),
    )

    def runner(tile, sources, output_dir, target_crs, parameters):
        del tile, parameters
        frame = gpd.read_file(sources["raw.road"])
        frame = frame.set_crs(target_crs) if frame.crs is None else frame.to_crs(target_crs)
        path = output_dir / "fused.gpkg"
        frame.to_file(path, driver="GPKG")
        return path, {"algorithm_id": "algo.test.line"}

    result = LargeAreaRuntimeService(max_workers=1).run(
        run_id="run-line",
        job_type="road",
        tile_manifest=_manifest(),
        slices=[LargeAreaSlice(name="road", geometry_family="line", sources={"raw.road": source}, runner=runner)],
        output_dir=tmp_path / "out-line",
        target_crs="EPSG:3857",
        parameters={},
    )

    fused = gpd.read_file(result.output_path)

    assert len(fused) == 1
    assert fused.iloc[0]["source_feature_id"] == "road-1"
    assert fused.geometry.iloc[0].equals(LineString([(0.0, 0.5), (2.0, 0.5)]))
    assert fused.geometry.iloc[0].length == pytest.approx(2.0)


def test_large_area_runtime_keeps_boundary_intersecting_polygon_when_representative_point_is_outside(
    tmp_path: Path,
) -> None:
    source = _write(
        tmp_path / "water.gpkg",
        gpd.GeoDataFrame(
            {"source_id": ["raw.water"], "source_feature_id": ["water-1"]},
            geometry=[box(-4.0, 0.25, 0.25, 0.75)],
            crs="EPSG:3857",
        ),
    )
    clip_boundary = gpd.GeoDataFrame({"name": ["clip"]}, geometry=[box(0.0, 0.0, 2.0, 1.0)], crs="EPSG:3857")

    def runner(tile, sources, output_dir, target_crs, parameters):
        del tile, parameters
        frame = gpd.read_file(sources["raw.water"])
        frame = frame.set_crs(target_crs) if frame.crs is None else frame.to_crs(target_crs)
        path = output_dir / "fused.gpkg"
        frame.to_file(path, driver="GPKG")
        return path, {"algorithm_id": "algo.test.boundary_polygon"}

    result = LargeAreaRuntimeService(max_workers=1).run(
        run_id="run-boundary-polygon",
        job_type="water",
        tile_manifest=_manifest(),
        slices=[
            LargeAreaSlice(
                name="water_polygon",
                geometry_family="polygon",
                sources={"raw.water": source},
                runner=runner,
            )
        ],
        output_dir=tmp_path / "out-boundary-polygon",
        target_crs="EPSG:3857",
        parameters={},
        clip_boundary=clip_boundary,
    )

    fused = gpd.read_file(result.output_path)

    assert len(fused) == 1
    assert fused.iloc[0]["source_feature_id"] == "water-1"
    assert fused.geometry.iloc[0].equals(box(0.0, 0.25, 0.25, 0.75))
    assert fused.geometry.iloc[0].within(clip_boundary.geometry.iloc[0])


def test_domain_line_runners_force_v7_config_target_crs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    road_base = _write(
        tmp_path / "osm_road.gpkg",
        gpd.GeoDataFrame({"osm_id": ["1"], "fclass": ["road"]}, geometry=[LineString([(0, 0), (1, 0)])], crs="EPSG:3857"),
    )
    road_supplement = _write(
        tmp_path / "overture_road.gpkg",
        gpd.GeoDataFrame({"id": ["2"], "class": ["road"]}, geometry=[LineString([(0, 0), (1, 0)])], crs="EPSG:3857"),
    )
    waterways_base = _write(
        tmp_path / "osm_waterways.gpkg",
        gpd.GeoDataFrame({"osm_id": ["3"], "fclass": ["river"]}, geometry=[LineString([(0, 1), (1, 1)])], crs="EPSG:3857"),
    )
    waterways_supplement = _write(
        tmp_path / "hydrorivers.gpkg",
        gpd.GeoDataFrame({"FID_1": ["4"], "waterway": ["river"]}, geometry=[LineString([(0, 1), (1, 1)])], crs="EPSG:3857"),
    )
    captured: dict[str, str] = {}

    class _Result:
        def __init__(self, algorithm_id: str) -> None:
            self.frame = gpd.GeoDataFrame(
                {"source_feature_id": [algorithm_id]},
                geometry=[LineString([(0, 0), (1, 0)])],
                crs="EPSG:4326",
            )
            self.stats = {"final_count": 1}
            self.config = {"target_crs": "EPSG:4326"}
            self.lineage = {"algorithm_id": algorithm_id}
            self.warnings = []

    def fake_road(base, supplement, *, config):
        del base, supplement
        captured["road"] = config.target_crs
        return _Result("algo.fusion.road.conflation.v7")

    def fake_waterways(base, supplement, *, config):
        del base, supplement
        captured["waterways"] = config.target_crs
        return _Result("algo.fusion.waterways.conflation.v7")

    monkeypatch.setattr(domain_runners, "run_road_conflation_v7", fake_road)
    monkeypatch.setattr(domain_runners, "run_waterways_conflation_v7", fake_waterways)

    domain_runners.run_road_tile(
        _manifest().tiles[0],
        {"raw.osm.road": road_base, "raw.overture.transportation": road_supplement},
        tmp_path / "road-out",
        "EPSG:4326",
        {"target_crs": "EPSG:32643"},
    )
    domain_runners.run_waterways_tile(
        _manifest().tiles[0],
        {"raw.osm.waterways": waterways_base, "raw.hydrorivers.water": waterways_supplement},
        tmp_path / "waterways-out",
        "EPSG:4326",
        {"target_crs": "EPSG:32643"},
    )

    assert captured == {"road": "EPSG:4326", "waterways": "EPSG:4326"}


def test_water_polygon_runner_assigns_source_id_before_fusion(tmp_path: Path) -> None:
    osm_water = _write(
        tmp_path / "osm_water.gpkg",
        gpd.GeoDataFrame(
            {"osm_id": [1]},
            geometry=[Polygon([(0.0, 0.0), (0.0, 1.0), (1.0, 1.0), (1.0, 0.0)])],
            crs="EPSG:3857",
        ),
    )
    hydrolakes = _write(
        tmp_path / "hydrolakes.gpkg",
        gpd.GeoDataFrame(
            {"Hylak_id": [11]},
            geometry=[Polygon([(1.2, 0.0), (1.2, 1.0), (2.0, 1.0), (2.0, 0.0)])],
            crs="EPSG:3857",
        ),
    )

    output_path, _stats = domain_runners.run_water_polygon_tile(
        _manifest().tiles[0],
        {"raw.osm.water": osm_water, "raw.hydrolakes.water": hydrolakes},
        tmp_path / "water-polygon-out",
        "EPSG:3857",
        {},
    )

    fused = gpd.read_file(output_path)

    assert set(fused["feature_kind"]) == {"polygon"}
    assert {"raw.osm.water", "raw.hydrolakes.water"}.issubset(set(fused["source_id"]))


def test_waterways_runner_assigns_source_id_before_v7_canonicalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    osm_waterways = _write(
        tmp_path / "osm_waterways.gpkg",
        gpd.GeoDataFrame(
            {"osm_id": ["osm-1"], "fclass": ["river"]},
            geometry=[LineString([(0.0, 0.0), (1.0, 0.0)])],
            crs="EPSG:3857",
        ),
    )
    hydrorivers = _write(
        tmp_path / "hydrorivers.gpkg",
        gpd.GeoDataFrame(
            {"HYRIV_ID": ["hydro-1"], "waterway": ["river"]},
            geometry=[LineString([(0.0, 0.2), (1.0, 0.2)])],
            crs="EPSG:3857",
        ),
    )

    class _Result:
        def __init__(self, frame: gpd.GeoDataFrame) -> None:
            self.frame = frame
            self.stats = {"final_count": len(frame)}
            self.config = {"target_crs": "EPSG:3857"}
            self.lineage = {"algorithm_id": "algo.fusion.waterways.conflation.v7"}
            self.warnings = []

    def fake_waterways(base, supplement, *, config):
        del config
        frame = gpd.GeoDataFrame(
            {
                "source_id": [
                    base["source_id"].iloc[0],
                    supplement["source_id"].iloc[0],
                ],
                "source_feature_id": [
                    base["source_feature_id"].iloc[0] if "source_feature_id" in base.columns else "base-1",
                    supplement["source_feature_id"].iloc[0] if "source_feature_id" in supplement.columns else "supplement-1",
                ],
            },
            geometry=[base.geometry.iloc[0], supplement.geometry.iloc[0]],
            crs=base.crs,
        )
        return _Result(frame)

    monkeypatch.setattr(domain_runners, "run_waterways_conflation_v7", fake_waterways)

    output_path, _stats = domain_runners.run_waterways_tile(
        _manifest().tiles[0],
        {"raw.osm.waterways": osm_waterways, "raw.hydrorivers.water": hydrorivers},
        tmp_path / "waterways-out",
        "EPSG:3857",
        {},
    )

    fused = gpd.read_file(output_path)

    assert set(fused["feature_kind"]) == {"line"}
    assert set(fused["source_id"]) == {"raw.osm.waterways", "raw.hydrorivers.water"}
