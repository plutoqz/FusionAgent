from __future__ import annotations

import json
from pathlib import Path

from schemas.agent import (
    RunArtifactMeta,
    RunEvent,
    RunPhase,
    RunStatus,
    RunTrigger,
    RunTriggerType,
    ValidationReport,
    WorkflowPlan,
    WorkflowTask,
    WorkflowTaskInput,
    WorkflowTaskOutput,
)
from schemas.fusion import JobType
from services.run_report_service import build_run_report_summary, render_run_reports


def test_render_run_reports_writes_chinese_english_and_json_evidence(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.zip"
    artifact.write_bytes(b"zip")
    status = _run_status(artifact)
    audit_events = _audit_events()

    summary = build_run_report_summary(
        status=status,
        plan=_plan(),
        audit_events=audit_events,
        artifact_path=artifact,
        telemetry_summary={"event_counts": {"run_succeeded": 1}},
        digest={"current_phase": "succeeded"},
    )

    outputs = render_run_reports(summary=summary, documents_dir=tmp_path / "documents")

    zh = Path(outputs["zh"]).read_text(encoding="utf-8")
    en = Path(outputs["en"]).read_text(encoding="utf-8")
    evidence = json.loads(Path(outputs["summary"]).read_text(encoding="utf-8"))
    assert "过程评价" in zh
    assert "结果评价" in zh
    assert "质量与证据边界" in zh
    assert "自进化证据" in zh
    assert "Process Evaluation" in en
    assert "Result Evaluation" in en
    assert "Quality And Evidence Boundary" in en
    assert "Self-Evolution Evidence" in en
    assert evidence["evaluation"]["process"]["telemetry"]["event_counts"]["run_succeeded"] == 1
    assert evidence["evaluation"]["result"]["artifact_metrics"]["artifact_validity"] is True
    assert evidence["source_coverage"][0]["selected_source_id"] == "catalog.flood.building"
    assert evidence["evaluation"]["self_evolution"]["boundary"].startswith("bounded policy hints")
    assert "quality_summary" in evidence
    assert "evidence_readiness" in evidence


def test_run_report_includes_large_area_runtime_evidence(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.gpkg"
    artifact.write_bytes(b"gpkg")
    status = _run_status(artifact)
    audit_events = _audit_events() + [
        RunEvent(
            timestamp="2026-05-28T00:00:07+00:00",
            kind="large_area_runtime_completed",
            phase=RunPhase.running,
            message="large area complete",
            details={
                "tile_count": 4,
                "stitched_feature_count": 12,
                "evidence_paths": {
                    "tile_manifest": str(tmp_path / "tile_manifest.json"),
                    "selected_sources": str(tmp_path / "selected_sources.json"),
                    "stitched_artifact": str(tmp_path / "stitched_artifact.json"),
                    "fusion_stats": str(tmp_path / "fusion_stats.json"),
                },
            },
        )
    ]

    summary = build_run_report_summary(
        status=status,
        plan=_plan(),
        audit_events=audit_events,
        artifact_path=artifact,
        source_semantic_contract={
            "height_policy": {
                "raster_height_sources": {"raw.google.building_height.raster": "height.tif"}
            }
        },
    )

    assert summary["large_area_runtime"]["tile_count"] == 4
    assert summary["large_area_runtime"]["stitched_feature_count"] == 12
    assert summary["large_area_runtime"]["evidence_paths"]["selected_sources"].endswith("selected_sources.json")
    assert (
        "raw.google.building_height.raster"
        in summary["source_semantic_contract"]["height_policy"]["raster_height_sources"]
    )


def test_run_report_includes_quality_summary_for_height_raster(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.gpkg"
    artifact.write_bytes(b"gpkg")
    status = _run_status(artifact)

    summary = build_run_report_summary(
        status=status,
        plan=_plan(),
        audit_events=_audit_events(),
        artifact_path=artifact,
        source_semantic_contract={
            "height_policy": {
                "raster_height_sources": {"raw.google.building_height.raster": "height.tif"},
                "height_fields": ["height"],
            }
        },
    )

    assert summary["quality_summary"]["target_capability"]["target_2_building_height_raster"] == {
        "supported": True,
        "raster_participated": True,
        "source_ids": ["raw.google.building_height.raster"],
    }
    assert summary["evidence_readiness"]["score"] == summary["quality_summary"]["evidence_readiness_score"]


def test_run_report_includes_bounded_poi_quality_boundary(tmp_path: Path) -> None:
    artifact = tmp_path / "poi.gpkg"
    artifact.write_bytes(b"gpkg")
    status = _run_status(artifact).model_copy(update={"job_type": JobType.poi})
    plan = _plan().model_copy(
        update={
            "tasks": [
                _plan().tasks[0].model_copy(
                    update={
                        "input": _plan().tasks[0].input.model_copy(
                            update={"data_type_id": "dt.poi.bundle", "data_source_id": "catalog.generic.poi"}
                        ),
                        "output": _plan().tasks[0].output.model_copy(update={"data_type_id": "dt.poi.fused"}),
                    }
                )
            ]
        }
    )
    events = _audit_events() + [
        RunEvent(
            timestamp="2026-05-29T00:00:07+00:00",
            kind="task_inputs_resolved",
            phase=RunPhase.running,
            message="poi inputs",
            details={
                "resolved_aoi": {"display_name": "Nairobi, Kenya", "bbox": [36.65, -1.45, 37.10, -1.10]},
                "component_coverage": {
                    "raw.osm.poi": {"feature_count": 5},
                    "raw.gns.poi": {"feature_count": 2},
                },
            },
        )
    ]

    summary = build_run_report_summary(
        status=status,
        plan=plan,
        audit_events=events,
        artifact_path=artifact,
        source_semantic_contract={"component_source_ids": ["raw.osm.poi", "raw.gns.poi"]},
    )

    poi = summary["quality_summary"]["target_capability"]["target_5_bounded_poi"]
    assert poi["bounded"] is True
    assert poi["aoi_bound"] == [36.65, -1.45, 37.10, -1.10]
    assert "unbounded POI entity alignment is unsupported" in summary["evidence_readiness"]["boundary"]["poi"]


def test_run_report_marks_partial_reference_coverage_as_degraded(tmp_path: Path) -> None:
    artifact = tmp_path / "road.gpkg"
    artifact.write_bytes(b"gpkg")
    status = _run_status(artifact).model_copy(update={"job_type": JobType.road})
    events = _audit_events() + [
        RunEvent(
            timestamp="2026-06-03T00:00:07+00:00",
            kind="task_inputs_resolved",
            phase=RunPhase.running,
            message="road inputs",
            details={
                "source_id": "catalog.flood.road",
                "selected_source_id": "catalog.flood.road",
                "component_coverage": {
                    "raw.osm.road": {"feature_count": 12, "coverage_status": "available"},
                    "raw.overture.transportation": {"feature_count": 0, "coverage_status": "empty"},
                },
            },
        )
    ]

    summary = build_run_report_summary(
        status=status,
        plan=_plan(),
        audit_events=events,
        artifact_path=artifact,
    )

    assert summary["degradation"]["state"] == "degraded"
    assert summary["degradation"]["reason_code"] == "PARTIAL_SOURCE_COVERAGE"
    assert summary["source_coverage"][-1]["coverage_state"] == "degraded"
    assert summary["source_coverage"][-1]["degraded_component_source_ids"] == ["raw.overture.transportation"]


def test_run_report_quality_summary_includes_recovery_operator_action(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.gpkg"
    artifact.write_bytes(b"gpkg")
    status = _run_status(artifact).model_copy(
        update={
            "phase": RunPhase.failed,
            "failure_summary": "download timed out | failure_category=SOURCE_DOWNLOAD_FAILED",
            "checkpoint": {"stage": "execution"},
        }
    )

    summary = build_run_report_summary(
        status=status,
        plan=_plan(),
        audit_events=_audit_events(),
        artifact_path=artifact,
    )

    recovery = summary["quality_summary"]["target_capability"]["target_9_recovery"]
    assert recovery["recoverable"] is True
    assert recovery["recovery_action"] == "redispatch_from_execution"
    assert recovery["operator_action"] == "no manual action required; recovery worker can redispatch from execution"


def _run_status(artifact: Path) -> RunStatus:
    return RunStatus(
        run_id="run-report",
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="need building data"),
        phase=RunPhase.succeeded,
        progress=100,
        target_crs="EPSG:4326",
        artifact=RunArtifactMeta(filename=artifact.name, path=str(artifact), size_bytes=artifact.stat().st_size),
        created_at="2026-05-27T00:00:00+00:00",
        updated_at="2026-05-27T00:01:00+00:00",
    )


def _plan() -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id="wf.run.report",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="need building data"),
        context={
            "retrieval": {"candidate_patterns": [{"pattern_id": "wp.flood.building.default"}]},
            "planning_mode": "task_driven",
        },
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id="algo.fusion.building.v1",
                input=WorkflowTaskInput(
                    data_type_id="dt.building.bundle",
                    data_source_id="catalog.flood.building",
                ),
                output=WorkflowTaskOutput(data_type_id="dt.building.fused"),
                kg_validated=True,
            )
        ],
        expected_output="building result",
        validation=ValidationReport(valid=True, inserted_transform_steps=0, issues=[]),
    )


def _audit_events() -> list[RunEvent]:
    return [
        RunEvent(
            timestamp="2026-05-27T00:00:01+00:00",
            kind="plan_created",
            phase=RunPhase.planning,
            message="plan",
        ),
        RunEvent(
            timestamp="2026-05-27T00:00:02+00:00",
            kind="plan_validated",
            phase=RunPhase.validating,
            message="validated",
        ),
        RunEvent(
            timestamp="2026-05-27T00:00:03+00:00",
            kind="task_inputs_resolved",
            phase=RunPhase.running,
            message="inputs",
            details={
                "source_id": "catalog.flood.building",
                "source_mode": "downloaded",
                "cache_hit": False,
                "component_coverage": {"raw.osm.building": {"feature_count": 2}},
            },
        ),
        RunEvent(
            timestamp="2026-05-27T00:00:04+00:00",
            kind="output_schema_validated",
            phase=RunPhase.running,
            message="schema",
            details={"artifact_validity": True, "missing_fields": []},
        ),
        RunEvent(
            timestamp="2026-05-27T00:00:05+00:00",
            kind="durable_learning_recorded",
            phase=RunPhase.running,
            message="learning",
        ),
        RunEvent(
            timestamp="2026-05-27T00:00:06+00:00",
            kind="run_succeeded",
            phase=RunPhase.succeeded,
            message="ok",
        ),
    ]
