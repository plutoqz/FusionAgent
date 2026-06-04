from pathlib import Path

import geopandas as gpd
from shapely.geometry import LineString, Polygon

from schemas.agent import DecisionCandidate, DecisionRecord, RunEvent, RunPhase, RunTrigger, RunTriggerType, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from services.artifact_evaluation_service import evaluate_agentic_run, evaluate_vector_artifact


def test_evaluate_vector_artifact_reports_polygon_metrics(tmp_path):
    shp_path = _write_polygon_fixture(tmp_path / "buildings.shp", count=2, crs="EPSG:32631")

    metrics = evaluate_vector_artifact(shp_path, required_fields=["geometry"])

    assert metrics["artifact_validity"] is True
    assert metrics["feature_count"] == 2
    assert metrics["crs"] == "EPSG:32631"
    assert metrics["geometry_types"] == ["Polygon"]
    assert metrics["total_area_sq_km"] > 0


def test_evaluate_vector_artifact_reports_line_metrics(tmp_path):
    shp_path = _write_line_fixture(tmp_path / "roads.shp", count=3, crs="EPSG:32631")

    metrics = evaluate_vector_artifact(shp_path, required_fields=["geometry"])

    assert metrics["artifact_validity"] is True
    assert metrics["feature_count"] == 3
    assert metrics["total_length_km"] > 0


def test_evaluate_vector_artifact_marks_missing_required_fields_invalid(tmp_path):
    shp_path = _write_polygon_fixture(tmp_path / "missing_fields.shp", count=1, crs="EPSG:32631")

    metrics = evaluate_vector_artifact(shp_path, required_fields=["geometry", "confidence"])

    assert metrics["artifact_validity"] is False
    assert metrics["missing_fields"] == ["confidence"]


def test_evaluate_vector_artifact_reads_gpkg_layer(tmp_path):
    gpkg_path = _write_polygon_fixture(tmp_path / "buildings.gpkg", count=2, crs="EPSG:4326")

    metrics = evaluate_vector_artifact(gpkg_path, required_fields=["geometry", "fid"])

    assert metrics["artifact_validity"] is True
    assert metrics["feature_count"] == 2
    assert metrics["bbox"]


def test_evaluate_vector_artifact_reports_aoi_containment(tmp_path):
    gpkg_path = _write_polygon_fixture(tmp_path / "buildings.gpkg", count=1, crs="EPSG:4326")

    metrics = evaluate_vector_artifact(
        gpkg_path,
        required_fields=["geometry"],
        requested_bbox=(-1.0, -1.0, 20.0, 20.0),
    )

    assert metrics["aoi_consistency"]["requested_bbox"] == [-1.0, -1.0, 20.0, 20.0]
    assert metrics["aoi_consistency"]["artifact_intersects_aoi"] is True


def test_evaluate_vector_artifact_reports_duplicate_and_invalid_geometry_rates(tmp_path):
    path = tmp_path / "quality.gpkg"
    polygon = Polygon([(0, 0), (0, 1), (1, 1), (1, 0)])
    invalid = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])
    frame = gpd.GeoDataFrame(
        {"source_id": ["a", "a", "b"]},
        geometry=[polygon, polygon, invalid],
        crs="EPSG:4326",
    )
    frame.to_file(path, driver="GPKG")

    metrics = evaluate_vector_artifact(path, required_fields=["geometry", "source_id"])

    assert metrics["duplicate_geometry_rate"] > 0
    assert metrics["invalid_geometry_rate"] > 0
    assert metrics["source_feature_counts"] == {"a": 2, "b": 1}


def test_evaluate_agentic_run_reports_trace_and_self_evolution_metrics() -> None:
    result = evaluate_agentic_run(
        plan=_make_plan_with_kg_path(),
        decision_records=_make_decisions_with_learning_adjustment(),
        audit_events=_make_successful_audit_events(),
        durable_learning_summary={"patterns": [{"entity_id": "wp.a", "total_runs": 3}]},
        manual_intervention_count=0,
    )

    assert result["kg_path_trace_completeness"] == 1.0
    assert result["decision_trace_completeness"] == 1.0
    assert result["autonomy_ratio"] == 1.0
    assert result["self_evolution_hint_available"] is True
    assert result["self_evolution_hint_used"] is True
    assert result["self_evolution_policy_adjustment"] != 0


def _write_polygon_fixture(path: Path, *, count: int, crs: str) -> Path:
    frame = gpd.GeoDataFrame(
        {"fid": list(range(count))},
        geometry=[
            Polygon([(idx * 10, 0), (idx * 10, 10), (idx * 10 + 10, 10), (idx * 10 + 10, 0)])
            for idx in range(count)
        ],
        crs=crs,
    )
    frame.to_file(path)
    return path


def _write_line_fixture(path: Path, *, count: int, crs: str) -> Path:
    frame = gpd.GeoDataFrame(
        {"fid": list(range(count))},
        geometry=[LineString([(0, idx * 10), (100, idx * 10)]) for idx in range(count)],
        crs=crs,
    )
    frame.to_file(path)
    return path


def _make_plan_with_kg_path() -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id="wf",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="x"),
        context={"retrieval": {"candidate_patterns": [{"pattern_id": "wp.a"}]}},
        tasks=[
            WorkflowTask(
                step=1,
                name="fusion",
                description="fusion",
                algorithm_id="algo.a",
                input=WorkflowTaskInput(data_type_id="dt.a", data_source_id="source.a"),
                output=WorkflowTaskOutput(data_type_id="dt.out"),
                kg_validated=True,
            )
        ],
        expected_output="out",
    )


def _make_decisions_with_learning_adjustment() -> list[DecisionRecord]:
    return [
        DecisionRecord(
            decision_type="pattern_selection",
            selected_id="wp.a",
            selected_score=0.9,
            rationale="test",
            candidates=[
                DecisionCandidate(
                    candidate_id="wp.a",
                    score=0.9,
                    reason="test",
                    evidence={"metrics": {"learning_adjustment": 0.1}},
                )
            ],
        )
    ]


def _make_successful_audit_events() -> list[RunEvent]:
    return [
        RunEvent(timestamp="2026-04-21T00:00:00+00:00", kind="plan_validated", phase=RunPhase.running, message="ok"),
        RunEvent(timestamp="2026-04-21T00:00:01+00:00", kind="task_inputs_resolved", phase=RunPhase.running, message="ok"),
        RunEvent(timestamp="2026-04-21T00:00:02+00:00", kind="durable_learning_recorded", phase=RunPhase.running, message="ok"),
        RunEvent(timestamp="2026-04-21T00:00:03+00:00", kind="run_succeeded", phase=RunPhase.succeeded, message="ok"),
    ]
