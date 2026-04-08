from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import LineString, Point, Polygon

from adapters.building_adapter import (
    _label_building_matches,
    _resolve_building_parameters,
    _split_building_one_to_one_by_thresholds,
)
from adapters.road_adapter import run_road_fusion
from agent.executor import ExecutionContext, WorkflowExecutor
from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import WorkflowPlan
from schemas.fusion import JobType


def test_selected_parameters_reach_handler_through_execution_context(tmp_path: Path) -> None:
    captured: dict = {}

    def handler(ctx: ExecutionContext) -> Path:
        captured["active_step"] = ctx.active_step
        captured["step_parameters"] = dict(ctx.step_parameters or {})
        return tmp_path / "dummy_output.shp"

    executor = WorkflowExecutor(
        InMemoryKGRepository(),
        algorithm_handlers={"algo.fusion.building.v1": handler},
    )

    plan = WorkflowPlan.model_validate(
        {
            "workflow_id": "wf_param_binding",
            "trigger": {"type": "user_query", "content": "binding"},
            "context": {},
            "tasks": [
                {
                    "step": 1,
                    "name": "building_fusion",
                    "description": "execute building fusion",
                    "algorithm_id": "algo.fusion.building.v1",
                    "input": {
                        "data_type_id": "dt.building.bundle",
                        "data_source_id": "upload.bundle",
                        "parameters": {
                            "match_threshold": 0.42,
                            "output_fields": ["osm_id", "confidence"],
                        },
                    },
                    "output": {"data_type_id": "dt.building.fused", "description": "out"},
                    "depends_on": [],
                    "is_transform": False,
                    "kg_validated": True,
                    "alternatives": [],
                }
            ],
            "expected_output": "building fused shapefile",
            "estimated_time": "unknown",
        }
    )

    # Handler doesn't read these, but keep context realistic.
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    osm_shp.write_text("", encoding="utf-8")
    ref_shp.write_text("", encoding="utf-8")

    context = ExecutionContext(
        run_id="run-1",
        job_type=JobType.building,
        osm_shp=osm_shp,
        ref_shp=ref_shp,
        output_dir=tmp_path,
        target_crs="EPSG:4326",
    )

    out = executor.execute_plan(plan, context, repair_records=[])

    assert out == tmp_path / "dummy_output.shp"
    assert captured["active_step"] == 1
    assert captured["step_parameters"]["match_threshold"] == 0.42
    assert captured["step_parameters"]["output_fields"] == ["osm_id", "confidence"]


def test_building_adapter_threshold_parameters_change_matching_and_one_to_one_routing() -> None:
    similarity_gdf = gpd.GeoDataFrame(
        {
            "idx": [1],
            "idx1": [1],
            "similarity": [0.35],
        },
        geometry=[Point(0, 0)],
        crs="EPSG:32643",
    )
    strict = _resolve_building_parameters({"match_similarity_threshold": 0.4})
    relaxed = _resolve_building_parameters({"match_similarity_threshold": 0.3})

    strict_labeled = _label_building_matches(
        similarity_gdf,
        match_similarity_threshold=strict.match_similarity_threshold,
    )
    relaxed_labeled = _label_building_matches(
        similarity_gdf,
        match_similarity_threshold=relaxed.match_similarity_threshold,
    )

    assert pd.isna(strict_labeled.loc[0, "label"])
    assert relaxed_labeled.loc[0, "label"] == "1"

    one_to_one = gpd.GeoDataFrame(
        {
            "sim_area": [0.5],
            "sim_shape": [0.2],
            "sim_overlap": [0.5],
        },
        geometry=[Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])],
        crs="EPSG:32643",
    )
    default_params = _resolve_building_parameters({})
    tuned_params = _resolve_building_parameters({"one_to_one_min_shape_similarity": 0.1})

    rejected_default, accepted_default = _split_building_one_to_one_by_thresholds(one_to_one, default_params)
    rejected_tuned, accepted_tuned = _split_building_one_to_one_by_thresholds(one_to_one, tuned_params)

    assert len(rejected_default) == 1
    assert accepted_default.empty
    assert rejected_tuned.empty
    assert len(accepted_tuned) == 1


def test_road_adapter_parameters_bind_into_legacy_module_and_postprocess(tmp_path: Path, monkeypatch) -> None:
    class FakeLegacyLine:
        ANGLE_THRESHOLD = 135
        SNAP_TOLERANCE = 1.0
        BUFFER_DIST = 20.0
        MAX_HAUSDORFF = 15.0

        def __init__(self) -> None:
            self.captured: dict = {"split_angles": []}

        def process_osm_data(self, gdf):
            return gdf

        def process_msft_data(self, gdf):
            return gdf

        def split_features_in_gdf(self, gdf, angle_threshold):
            self.captured["split_angles"].append(angle_threshold)
            return gdf

        def match_and_fuse(self, gdf_osm, gdf_msft, _idx):
            self.captured["buffer_dist"] = self.BUFFER_DIST
            self.captured["max_hausdorff"] = self.MAX_HAUSDORFF
            return gdf_osm.copy(), 0, 0, 0

        def process_roads(self, input_path, output_path, buffer_distance):
            self.captured["dedupe_buffer"] = buffer_distance
            self.captured["input_path"] = input_path
            self.captured["output_path"] = output_path

    fake_legacy = FakeLegacyLine()
    monkeypatch.setattr("adapters.road_adapter.load_legacy_module", lambda *_args, **_kwargs: fake_legacy)
    monkeypatch.setattr(gpd.GeoDataFrame, "to_file", lambda self, *args, **kwargs: None, raising=False)

    base_gdf = gpd.GeoDataFrame(
        {
            "osm_id": [1],
            "FID_1": [1],
            "fclass": ["road"],
        },
        geometry=[LineString([(0, 0), (1, 1)])],
        crs="EPSG:4326",
    )
    dedup_gdf = gpd.GeoDataFrame(
        {
            "osm_id": [1],
            "FID_1": [1],
            "fclass": ["road"],
        },
        geometry=[LineString([(0, 0), (1, 1)])],
        crs="EPSG:32643",
    )

    def fake_read_file(path):
        raw = str(path)
        if raw.endswith("osm.shp") or raw.endswith("ref.shp"):
            return base_gdf.copy()
        if raw.endswith("fused_roads_dedup.shp"):
            return dedup_gdf.copy()
        raise AssertionError(f"unexpected read_file path: {path}")

    monkeypatch.setattr("adapters.road_adapter.gpd.read_file", fake_read_file)

    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    osm_shp.write_text("", encoding="utf-8")
    ref_shp.write_text("", encoding="utf-8")

    out = run_road_fusion(
        osm_shp=osm_shp,
        ref_shp=ref_shp,
        output_dir=tmp_path / "output",
        parameters={
            "angle_threshold_deg": 99,
            "snap_tolerance_m": 2.5,
            "match_buffer_m": 33.0,
            "max_hausdorff_m": 7.0,
            "dedupe_buffer_m": 8.5,
        },
    )

    assert out == tmp_path / "output" / "fused_roads.shp"
    assert fake_legacy.captured["split_angles"] == [99, 99]
    assert fake_legacy.captured["buffer_dist"] == 33.0
    assert fake_legacy.captured["max_hausdorff"] == 7.0
    assert fake_legacy.captured["dedupe_buffer"] == 8.5
    assert fake_legacy.SNAP_TOLERANCE == 2.5
