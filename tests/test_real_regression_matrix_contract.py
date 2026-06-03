from __future__ import annotations

from pathlib import Path

import pytest

from schemas.agent import RunArtifactMeta, RunEvent, RunPhase, RunStatus, RunTrigger, RunTriggerType, ValidationReport, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from schemas.fusion import JobType
from services.run_report_service import build_run_report_summary


@pytest.mark.parametrize(
    ("job_type", "selected_source_id", "component_source_ids"),
    [
        (JobType.building, "catalog.flood.building", ["raw.osm.building", "raw.microsoft.building"]),
        (JobType.road, "catalog.flood.road", ["raw.osm.road", "raw.overture.transportation"]),
        (JobType.water, "catalog.flood.water", ["raw.osm.water", "raw.hydrolakes.water"]),
        (JobType.poi, "catalog.generic.poi", ["raw.osm.poi", "raw.gns.poi"]),
    ],
)
@pytest.mark.parametrize("scope", ["small", "large"])
def test_four_type_real_regression_matrix_requires_source_and_large_area_evidence(
    tmp_path: Path,
    job_type: JobType,
    selected_source_id: str,
    component_source_ids: list[str],
    scope: str,
) -> None:
    artifact = tmp_path / f"{job_type.value}-{scope}.gpkg"
    artifact.write_bytes(b"gpkg")
    audit_events = _matrix_events(
        tmp_path=tmp_path,
        selected_source_id=selected_source_id,
        component_source_ids=component_source_ids,
        large=scope == "large",
    )

    summary = build_run_report_summary(
        status=_status(job_type, artifact),
        plan=_plan(job_type, selected_source_id),
        audit_events=audit_events,
        artifact_path=artifact,
        source_semantic_contract={"component_source_ids": component_source_ids},
    )

    assert summary["source_coverage"]
    assert summary["source_coverage"][0]["selected_source_id"] == selected_source_id
    assert set(summary["source_coverage"][0]["component_coverage"]) >= set(component_source_ids)
    assert summary["evaluation"]["result"]["artifact_metrics"]["artifact_validity"] is True
    if scope == "large":
        evidence_paths = summary["large_area_runtime"]["evidence_paths"]
        assert evidence_paths["tile_manifest"].endswith("tile_manifest.json")
        assert evidence_paths["fusion_stats"].endswith("fusion_stats.json")
        assert summary["large_area_runtime"]["tile_count"] >= 1


def _status(job_type: JobType, artifact: Path) -> RunStatus:
    return RunStatus(
        run_id=f"matrix-{job_type.value}",
        job_type=job_type,
        trigger=RunTrigger(type=RunTriggerType.user_query, content=f"{job_type.value} matrix"),
        phase=RunPhase.succeeded,
        progress=100,
        target_crs="EPSG:4326",
        artifact=RunArtifactMeta(filename=artifact.name, path=str(artifact), size_bytes=artifact.stat().st_size),
        created_at="2026-06-03T00:00:00+00:00",
        finished_at="2026-06-03T00:00:01+00:00",
    )


def _plan(job_type: JobType, source_id: str) -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id=f"wf.matrix.{job_type.value}",
        trigger=RunTrigger(type=RunTriggerType.user_query, content=f"{job_type.value} matrix"),
        context={"retrieval": {"data_sources": [{"source_id": source_id}]}},
        tasks=[
            WorkflowTask(
                step=1,
                name=f"{job_type.value}_fusion",
                description="matrix fusion",
                algorithm_id=f"algo.fusion.{job_type.value}.v1",
                input=WorkflowTaskInput(data_type_id=f"dt.{job_type.value}.bundle", data_source_id=source_id),
                output=WorkflowTaskOutput(data_type_id=f"dt.{job_type.value}.fused"),
                kg_validated=True,
            )
        ],
        expected_output=f"{job_type.value} fused",
        validation=ValidationReport(valid=True),
    )


def _matrix_events(
    *,
    tmp_path: Path,
    selected_source_id: str,
    component_source_ids: list[str],
    large: bool,
) -> list[RunEvent]:
    events = [
        RunEvent(
            timestamp="2026-06-03T00:00:00+00:00",
            kind="task_inputs_resolved",
            phase=RunPhase.running,
            message="inputs",
            details={
                "source_id": selected_source_id,
                "selected_source_id": selected_source_id,
                "component_coverage": {
                    source_id: {"feature_count": 1, "coverage_status": "available"}
                    for source_id in component_source_ids
                },
            },
        ),
        RunEvent(
            timestamp="2026-06-03T00:00:01+00:00",
            kind="output_schema_validated",
            phase=RunPhase.running,
            message="schema",
            details={"artifact_validity": True},
        ),
    ]
    if large:
        events.append(
            RunEvent(
                timestamp="2026-06-03T00:00:02+00:00",
                kind="large_area_runtime_completed",
                phase=RunPhase.running,
                message="large complete",
                details={
                    "tile_count": 1,
                    "stitched_feature_count": 1,
                    "evidence_paths": {
                        "tile_manifest": str(tmp_path / "tile_manifest.json"),
                        "selected_sources": str(tmp_path / "selected_sources.json"),
                        "stitched_artifact": str(tmp_path / "stitched_artifact.json"),
                        "fusion_stats": str(tmp_path / "fusion_stats.json"),
                    },
                },
            )
        )
    return events
