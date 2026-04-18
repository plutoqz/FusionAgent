from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from agent.executor import ExecutionContext, WorkflowExecutor
from schemas.agent import ValidationReport, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from schemas.fusion import JobType


def _write_shapefile(path: Path, frame: gpd.GeoDataFrame) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path)
    return path


def _build_sample_inputs(tmp_path: Path) -> tuple[Path, Path]:
    osm = gpd.GeoDataFrame(
        {
            "osm_id": [1, 2],
            "fclass": ["building", "building"],
            "name": ["A", "B"],
            "type": ["residential", "residential"],
        },
        geometry=[
            Polygon([(0, 0), (0, 10), (10, 10), (10, 0)]),
            Polygon([(20, 20), (20, 30), (30, 30), (30, 20)]),
        ],
        crs="EPSG:3857",
    )
    ref = gpd.GeoDataFrame(
        {
            "confidence": [0.9, 0.8],
            "area_in_me": [100.0, 100.0],
            "longitude": [1.0, 2.0],
            "latitude": [1.0, 2.0],
        },
        geometry=[
            Polygon([(1, 1), (1, 9), (9, 9), (9, 1)]),
            Polygon([(40, 40), (40, 50), (50, 50), (50, 40)]),
        ],
        crs="EPSG:3857",
    )
    osm_path = _write_shapefile(tmp_path / "osm" / "osm.shp", osm)
    ref_path = _write_shapefile(tmp_path / "ref" / "ref.shp", ref)
    return osm_path, ref_path


def test_run_building_fusion_safe_merges_matched_and_unmatched_buildings(tmp_path: Path) -> None:
    from adapters.building_adapter import run_building_fusion_safe

    osm_path, ref_path = _build_sample_inputs(tmp_path)
    output_shp = run_building_fusion_safe(
        osm_shp=osm_path,
        ref_shp=ref_path,
        output_dir=tmp_path / "output",
        target_crs="EPSG:3857",
        field_mapping={},
        debug=False,
        parameters={"match_similarity_threshold": 0.3},
    )

    result = gpd.read_file(output_shp)

    assert output_shp.exists()
    assert len(result) == 3
    assert result.columns.tolist() == [
        "osm_id",
        "fclass",
        "name",
        "type",
        "longitude",
        "latitude",
        "area_in_me",
        "confidence",
        "geometry",
    ]
    assert int(result.geometry.is_empty.sum()) == 0
    assert int(result.geometry.isna().sum()) == 0

    matched = result.loc[result["osm_id"] == 1].iloc[0]
    assert matched["confidence"] == pytest.approx(0.9)
    assert matched["fclass"] == "building"
    assert matched["name"] == "A"

    unmatched_osm = result.loc[result["osm_id"] == 2].iloc[0]
    assert unmatched_osm["confidence"] == pytest.approx(1.0)
    assert unmatched_osm["name"] == "B"

    unmatched_ref = result.loc[result["osm_id"].isna()].iloc[0]
    assert unmatched_ref["fclass"] == "ref_building"
    assert unmatched_ref["confidence"] == pytest.approx(0.8)


def test_workflow_executor_falls_back_to_safe_building_algorithm_for_large_inputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    osm_path, ref_path = _build_sample_inputs(tmp_path)
    monkeypatch.setenv("GEOFUSION_BUILDING_LEGACY_MAX_FEATURES", "1")

    class _DummyRepo:
        @staticmethod
        def get_alternative_algorithms(_algorithm_id: str, limit: int = 3) -> list[object]:
            return []

    plan = WorkflowPlan(
        workflow_id="wf.building.safe.fallback",
        trigger={"type": "user_query", "content": "building"},
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id="algo.fusion.building.v1",
                input=WorkflowTaskInput(
                    data_type_id="dt.building.bundle",
                    data_source_id="upload.bundle",
                    parameters={"match_similarity_threshold": 0.3},
                ),
                output=WorkflowTaskOutput(data_type_id="dt.building.fused", description=""),
                depends_on=[],
                is_transform=False,
                kg_validated=True,
                alternatives=["algo.fusion.building.safe"],
            )
        ],
        expected_output="building result",
        validation=ValidationReport(valid=True, inserted_transform_steps=0, issues=[]),
    )
    context = ExecutionContext(
        run_id="run-safe-fallback",
        job_type=JobType.building,
        osm_shp=osm_path,
        ref_shp=ref_path,
        output_dir=tmp_path / "output-fallback",
        target_crs="EPSG:3857",
        field_mapping={},
        debug=False,
        alternative_data_sources=[],
    )

    executor = WorkflowExecutor(_DummyRepo())
    repair_records = []

    output_shp = executor.execute_plan(plan=plan, context=context, repair_records=repair_records)
    result = gpd.read_file(output_shp)

    assert output_shp.exists()
    assert len(result) == 3
    assert len(repair_records) == 2
    assert repair_records[0].success is False
    assert repair_records[0].from_algorithm == "algo.fusion.building.v1"
    assert repair_records[1].success is True
    assert repair_records[1].to_algorithm == "algo.fusion.building.safe"


def test_run_building_fusion_safe_normalizes_invalid_reference_confidence(tmp_path: Path) -> None:
    from adapters.building_adapter import run_building_fusion_safe

    osm = gpd.GeoDataFrame(
        {"osm_id": [1], "fclass": ["building"], "name": ["A"], "type": ["residential"]},
        geometry=[Polygon([(0, 0), (0, 10), (10, 10), (10, 0)])],
        crs="EPSG:3857",
    )
    ref = gpd.GeoDataFrame(
        {"confidence": [-1.0], "area_in_me": [100.0], "longitude": [1.0], "latitude": [1.0]},
        geometry=[Polygon([(1, 1), (1, 9), (9, 9), (9, 1)])],
        crs="EPSG:3857",
    )
    osm_path = _write_shapefile(tmp_path / "osm-neg" / "osm.shp", osm)
    ref_path = _write_shapefile(tmp_path / "ref-neg" / "ref.shp", ref)

    output_shp = run_building_fusion_safe(
        osm_shp=osm_path,
        ref_shp=ref_path,
        output_dir=tmp_path / "output-neg",
        target_crs="EPSG:3857",
        field_mapping={},
        debug=False,
        parameters={"match_similarity_threshold": 0.3},
    )
    result = gpd.read_file(output_shp)

    assert len(result) == 1
    assert float(result.iloc[0]["confidence"]) == pytest.approx(1.0)
