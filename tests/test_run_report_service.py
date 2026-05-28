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
    assert "自进化证据" in zh
    assert "Process Evaluation" in en
    assert "Result Evaluation" in en
    assert "Self-Evolution Evidence" in en
    assert evidence["evaluation"]["process"]["telemetry"]["event_counts"]["run_succeeded"] == 1
    assert evidence["evaluation"]["result"]["artifact_metrics"]["artifact_validity"] is True
    assert evidence["source_coverage"][0]["selected_source_id"] == "catalog.flood.building"
    assert evidence["evaluation"]["self_evolution"]["boundary"].startswith("bounded policy hints")


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
