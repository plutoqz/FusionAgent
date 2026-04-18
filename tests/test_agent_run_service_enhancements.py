import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
from shapely.geometry import box

from schemas.agent import (
    RepairRecord,
    RunCreateRequest,
    RunInputStrategy,
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
from services.artifact_registry import ArtifactRecord
from services.agent_run_service import AgentRunService
from services.aoi_resolution_service import ResolvedAOI
from services.input_acquisition_service import ResolvedRunInputs


def _write_dummy_zip(path: Path) -> bytes:
    with ZipFile(path, "w") as zf:
        zf.writestr("dummy.shp", b"shp")
        zf.writestr("dummy.shx", b"shx")
        zf.writestr("dummy.dbf", b"dbf")
    return path.read_bytes()


def _write_polygon_bundle_zip(path: Path, geometries: list, *, crs: str = "EPSG:4326") -> Path:
    bundle_dir = path.parent / path.stem
    bundle_dir.mkdir(parents=True, exist_ok=True)
    shp_path = bundle_dir / "artifact.shp"
    gdf = gpd.GeoDataFrame({"feature_id": list(range(1, len(geometries) + 1))}, geometry=geometries, crs=crs)
    gdf.to_file(shp_path)
    with ZipFile(path, "w") as zf:
        for file in bundle_dir.iterdir():
            if file.is_file():
                zf.write(file, arcname=file.name)
    return path


def _iso_now_minus(*, days: int = 0, hours: int = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days, hours=hours)).isoformat()


def _build_plan(
    *,
    workflow_id: str,
    revision: int,
    algorithm_id: str = "algo.fusion.building.v1",
    include_reusable_artifacts: bool = False,
) -> WorkflowPlan:
    retrieval = {"candidate_patterns": [{"pattern_id": "wp.flood.building.default", "success_rate": 0.92}]}
    if include_reusable_artifacts:
        retrieval["reusable_artifacts"] = [
            {
                "artifact_id": "artifact-prior-1",
                "artifact_path": "/tmp/artifact-prior-1.zip",
                "created_at": "2026-04-06T00:00:00+00:00",
            }
        ]
    return WorkflowPlan(
        workflow_id=workflow_id,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        context={
            "intent": {
                "job_type": "building",
                "profile_source": "default_task",
                "task_bundle": {
                    "bundle_id": "task_bundle.direct_request",
                    "requested_tasks": ["task.building.fusion"],
                    "requires_disaster_profile": False,
                },
            },
            "retrieval": retrieval,
            "selection_reason": "initial" if revision == 1 else "replanned_after_failure",
            "llm_provider": "mock",
            "plan_revision": revision,
            "planning_mode": "task_driven",
        },
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id=algorithm_id,
                input=WorkflowTaskInput(data_type_id="dt.building.bundle", data_source_id="upload.bundle", parameters={}),
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


def _build_auto_request(*, spatial_extent: str = "bbox(0,0,1,1)") -> RunCreateRequest:
    return RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content="need building data",
            spatial_extent=spatial_extent,
        ),
        target_crs="EPSG:32643",
        field_mapping={},
        debug=False,
        input_strategy=RunInputStrategy.task_driven_auto,
    )


def _resolved_nairobi_aoi() -> ResolvedAOI:
    return ResolvedAOI(
        query="Nairobi, Kenya",
        display_name="Nairobi, Nairobi County, Kenya",
        country_name="Kenya",
        country_code="ke",
        bbox=(36.65, -1.45, 37.10, -1.10),
        confidence=0.97,
        selection_reason="single_high_confidence_candidate",
        candidates=(),
    )


def test_agent_run_service_updates_status_and_records_feedback(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")

    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp, fused_shp]:
        path.write_text("dummy", encoding="utf-8")

    plan = WorkflowPlan(
        workflow_id="wf_service",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        context={
            "intent": {
                "job_type": "building",
                "profile_source": "default_task",
                "task_bundle": {
                    "bundle_id": "task_bundle.direct_request",
                    "requested_tasks": ["task.building.fusion"],
                    "requires_disaster_profile": False,
                },
            },
            "retrieval": {
                "candidate_patterns": [{"pattern_id": "wp.flood.building.default", "success_rate": 0.90}],
                "reusable_artifacts": [
                    {
                        "artifact_id": "artifact-prior-1",
                        "artifact_path": "/tmp/artifact-prior-1.zip",
                        "created_at": "2026-04-06T00:00:00+00:00",
                    }
                ],
            },
            "selection_reason": "initial",
            "llm_provider": "mock",
            "plan_revision": 1,
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
                    data_source_id="upload.bundle",
                    parameters={
                        "match_similarity_threshold": 0.5,
                        "one_to_one_min_overlap_similarity": 0.3,
                    },
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

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    def fake_execute_plan(*, plan, context, repair_records, **_kwargs):
        repair_records.append(
            RepairRecord(
                attempt_no=1,
                strategy="alternative_algorithm",
                step=1,
                message="Recovered with safe algorithm",
                success=True,
                timestamp="2026-04-01T00:00:00+00:00",
                reason_code="alternative_algorithm_succeeded",
                from_algorithm="algo.fusion.building.v1",
                to_algorithm="algo.fusion.building.safe",
            )
        )
        return fused_shp

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)
    artifact_zip.write_bytes(b"zip")

    osm_zip = tmp_path / "osm.zip"
    ref_zip = tmp_path / "ref.zip"
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        target_crs="EPSG:32643",
        field_mapping={},
        debug=False,
    )

    status = service.create_run(
        request=request,
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(osm_zip),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(ref_zip),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert latest.plan_revision == 1
    assert latest.attempt_no == 1
    assert latest.audit_path
    assert latest.event_count >= 5
    assert latest.last_event is not None
    assert latest.last_event.kind == "run_succeeded"
    assert latest.decision_records
    assert latest.decision_records[0].decision_type == "pattern_selection"
    assert latest.decision_records[0].selected_id == "wp.flood.building.default"
    decision_types = {record.decision_type for record in latest.decision_records}
    assert {
        "pattern_selection",
        "data_source_selection",
        "artifact_reuse_selection",
        "parameter_strategy",
        "output_schema_policy",
    } <= decision_types
    for record in latest.decision_records:
        assert record.candidates
        assert set(record.candidates[0].evidence.keys()) == {"metrics", "meta"}
    assert latest.artifact_reuse is not None
    assert latest.artifact_reuse.reused is False
    assert latest.artifact_reuse.freshness_status == "candidate_available"
    assert latest.healing_summary["successful_repairs"] == 1
    assert latest.healing_summary["last_reason_code"] == "alternative_algorithm_succeeded"
    assert service.kg_repo.feedback_history[-1].pattern_id == "wp.flood.building.default"
    assert service.kg_repo.durable_learning_records[-1].run_id == status.run_id
    assert service.kg_repo.durable_learning_records[-1].success is True
    assert service.kg_repo.durable_learning_records[-1].output_data_type == "dt.building.fused"
    assert service.kg_repo.durable_learning_records[-1].metadata["planning_mode"] == "task_driven"
    assert service.kg_repo.durable_learning_records[-1].metadata["profile_source"] == "default_task"
    assert (
        service.kg_repo.durable_learning_records[-1].metadata["task_bundle"]["bundle_id"]
        == "task_bundle.direct_request"
    )
    audit_events = service.get_audit_events(status.run_id)
    plan_created = next(event for event in audit_events if event.kind == "plan_created")
    assert plan_created.details["effective_parameters"]["1"]["match_similarity_threshold"] == 0.5
    assert plan_created.details["effective_parameters"]["1"]["one_to_one_min_overlap_similarity"] == 0.3
    assert plan_created.details["planning_mode"] == "task_driven"
    assert plan_created.details["profile_source"] == "default_task"
    assert plan_created.details["task_bundle"]["bundle_id"] == "task_bundle.direct_request"
    registry_path = (tmp_path / "runs" / "artifact_registry.json")
    assert registry_path.exists()
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    records = payload.get("records", [])
    assert any(record.get("artifact_id") == status.run_id for record in records)


def test_run_status_records_planning_mode_and_profile_source(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp, fused_shp]:
        path.write_text("dummy", encoding="utf-8")
    artifact_zip.write_bytes(b"zip")

    plan = _build_plan(workflow_id="wf_task_mode", revision=1)

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(type=RunTriggerType.user_query, content="need building and road data for Gilgit, Pakistan"),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    saved_plan = service.get_plan(status.run_id)
    assert saved_plan is not None
    assert saved_plan.context["planning_mode"] == "task_driven"
    assert saved_plan.context["intent"]["profile_source"] == "default_task"
    assert saved_plan.context["intent"]["task_bundle"]["bundle_id"] == "task_bundle.direct_request"
    durable_record = service.kg_repo.durable_learning_records[-1]
    assert durable_record.metadata["planning_mode"] == "task_driven"
    assert durable_record.metadata["profile_source"] == "default_task"
    assert durable_record.metadata["task_bundle"]["bundle_id"] == "task_bundle.direct_request"


def test_agent_run_service_task_driven_auto_prepares_inputs_before_execution(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "resolved_osm.shp"
    ref_shp = tmp_path / "resolved_ref.shp"
    fused_shp = tmp_path / "fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp, fused_shp]:
        path.write_text("dummy", encoding="utf-8")
    artifact_zip.write_bytes(b"zip")

    plan = _build_plan(workflow_id="wf_auto_inputs", revision=1)
    plan.tasks[0].input.data_source_id = "catalog.flood.building"

    prepared_dir = tmp_path / "prepared"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    resolved = ResolvedRunInputs(
        osm_zip_path=prepared_dir / "osm.zip",
        ref_zip_path=prepared_dir / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.flood.building",
        cache_hit=False,
        version_token="v1",
    )
    resolved.osm_zip_path.write_bytes(b"osm")
    resolved.ref_zip_path.write_bytes(b"ref")

    captured: dict[str, object] = {}

    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    def fake_resolve_task_driven_inputs(**kwargs):
        captured.update(kwargs)
        return resolved

    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", fake_resolve_task_driven_inputs)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=_build_auto_request(),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert captured["source_id"] == "catalog.flood.building"
    assert captured["required_output_type"] == "dt.building.bundle"
    assert Path(captured["input_dir"]).name == "input"

    audit_events = service.get_audit_events(status.run_id)
    created = next(event for event in audit_events if event.kind == "run_created")
    assert created.details["input_strategy"] == "task_driven_auto"
    assert created.details["osm_zip_name"] is None
    assert created.details["ref_zip_name"] is None

    resolved_event = next(event for event in audit_events if event.kind == "task_inputs_resolved")
    assert resolved_event.details["input_strategy"] == "task_driven_auto"
    assert resolved_event.details["source_mode"] == "downloaded"
    assert resolved_event.details["source_id"] == "catalog.flood.building"
    assert resolved_event.details["cache_hit"] is False
    assert resolved_event.details["version_token"] == "v1"
    assert resolved_event.details["osm_zip_name"] == "osm.zip"
    assert resolved_event.details["ref_zip_name"] == "ref.zip"


def test_agent_run_service_resolves_nairobi_before_input_materialization(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "resolved_osm.shp"
    ref_shp = tmp_path / "resolved_ref.shp"
    fused_shp = tmp_path / "fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp, fused_shp]:
        path.write_text("dummy", encoding="utf-8")
    artifact_zip.write_bytes(b"zip")

    plan = _build_plan(workflow_id="wf_nairobi_auto", revision=1)
    plan.trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="fuse building and road data for Nairobi, Kenya",
    )
    plan.tasks[0].input.data_source_id = "catalog.earthquake.building"

    prepared_dir = tmp_path / "prepared"
    prepared_dir.mkdir(parents=True, exist_ok=True)
    resolved_inputs = ResolvedRunInputs(
        osm_zip_path=prepared_dir / "osm.zip",
        ref_zip_path=prepared_dir / "ref.zip",
        source_mode="downloaded",
        source_id="catalog.earthquake.building",
        cache_hit=False,
        version_token="ke-v1",
    )
    resolved_inputs.osm_zip_path.write_bytes(b"osm")
    resolved_inputs.ref_zip_path.write_bytes(b"ref")

    captured: dict[str, object] = {}
    resolved_aoi = _resolved_nairobi_aoi()

    monkeypatch.setattr(service.aoi_resolution_service, "resolve", lambda query: resolved_aoi)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    def fake_resolve_task_driven_inputs(**kwargs):
        captured.update(kwargs)
        return resolved_inputs

    monkeypatch.setattr(service.input_acquisition_service, "resolve_task_driven_inputs", fake_resolve_task_driven_inputs)
    monkeypatch.setattr(
        "services.agent_run_service.validate_zip_has_shapefile",
        lambda zip_path, *_args, **_kwargs: osm_shp if Path(zip_path).name.startswith("osm") else ref_shp,
    )
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: fused_shp)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.user_query,
                content="fuse building and road data for Nairobi, Kenya",
            ),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
            input_strategy=RunInputStrategy.task_driven_auto,
        ),
        osm_zip_name=None,
        osm_zip_bytes=None,
        ref_zip_name=None,
        ref_zip_bytes=None,
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert captured["source_id"] == "catalog.earthquake.building"
    assert captured["required_output_type"] == "dt.building.bundle"
    assert captured["resolved_aoi"] == resolved_aoi
    assert captured["request_bbox"] == resolved_aoi.bbox

    audit_events = service.get_audit_events(status.run_id)
    aoi_event = next(event for event in audit_events if event.kind == "aoi_resolved")
    assert aoi_event.details["display_name"] == "Nairobi, Nairobi County, Kenya"
    assert aoi_event.details["country_code"] == "ke"
    assert aoi_event.details["bbox"] == [36.65, -1.45, 37.10, -1.10]

    resolved_event = next(event for event in audit_events if event.kind == "task_inputs_resolved")
    assert resolved_event.details["resolved_aoi"]["country_code"] == "ke"
    assert resolved_event.details["resolved_aoi"]["display_name"] == "Nairobi, Nairobi County, Kenya"


def test_agent_run_service_directly_reuses_existing_artifact(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")

    reusable_created_at = _iso_now_minus(hours=1)
    source_artifact = _write_polygon_bundle_zip(tmp_path / "artifact-source.zip", [box(0, 0, 1, 1)], crs="EPSG:32643")
    service.artifact_registry.register(
        ArtifactRecord(
            artifact_id="artifact-source",
            artifact_path=str(source_artifact),
            job_type="building",
            disaster_type="flood",
            created_at=reusable_created_at,
            output_fields=[],
            bbox=(0.0, 0.0, 1.0, 1.0),
            output_data_type="dt.building.fused",
            target_crs="EPSG:32643",
            meta={"note": "direct"},
        )
    )

    plan = _build_plan(workflow_id="wf_direct", revision=1)
    plan.context["retrieval"]["reusable_artifacts"] = [
        {
            "artifact_id": "artifact-source",
            "artifact_path": str(source_artifact),
            "created_at": reusable_created_at,
            "bbox": [0.0, 0.0, 1.0, 1.0],
        }
    ]

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    def fail_execute_plan(**_kwargs):
        raise AssertionError("executor should not run when direct reuse succeeds")

    monkeypatch.setattr(service.executor, "execute_plan", fail_execute_plan)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.disaster_event,
                content="building",
                disaster_type="flood",
                spatial_extent="bbox(0,0,1,1)",
            ),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert latest.artifact is not None
    assert Path(latest.artifact.path).exists()
    assert Path(latest.artifact.path).parent.name == "output"
    assert latest.artifact_reuse is not None
    assert latest.artifact_reuse.reused is True
    assert latest.artifact_reuse.artifact_id == "artifact-source"
    assert latest.artifact_reuse.freshness_status == "direct_reused"
    audit_events = service.get_audit_events(status.run_id)
    plan_created = next(event for event in audit_events if event.kind == "plan_created")
    assert "effective_parameters" in plan_created.details
    reuse_event = next(event for event in audit_events if event.kind == "artifact_reuse_applied")
    assert reuse_event.details["reuse_mode"] == "direct"
    assert reuse_event.details["source_artifact_id"] == "artifact-source"


def test_agent_run_service_clips_reused_artifact_when_request_bbox_is_smaller(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")

    reusable_created_at = _iso_now_minus(hours=1)
    source_artifact = _write_polygon_bundle_zip(
        tmp_path / "artifact-clip-source.zip",
        [box(0, 0, 4, 4)],
        crs="EPSG:32643",
    )
    service.artifact_registry.register(
        ArtifactRecord(
            artifact_id="artifact-clip-source",
            artifact_path=str(source_artifact),
            job_type="building",
            disaster_type="flood",
            created_at=reusable_created_at,
            output_fields=[],
            bbox=(0.0, 0.0, 4.0, 4.0),
            output_data_type="dt.building.fused",
            target_crs="EPSG:32643",
            meta={"note": "clip"},
        )
    )

    plan = _build_plan(workflow_id="wf_clip", revision=1)
    plan.context["retrieval"]["reusable_artifacts"] = [
        {
            "artifact_id": "artifact-clip-source",
            "artifact_path": str(source_artifact),
            "created_at": reusable_created_at,
            "bbox": [0.0, 0.0, 4.0, 4.0],
        }
    ]

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    def fail_execute_plan(**_kwargs):
        raise AssertionError("executor should not run when clip reuse succeeds")

    monkeypatch.setattr(service.executor, "execute_plan", fail_execute_plan)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.disaster_event,
                content="building",
                disaster_type="flood",
                spatial_extent="bbox(1,1,2,2)",
            ),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert latest.artifact is not None
    clipped_zip = Path(latest.artifact.path)
    assert clipped_zip.exists()
    clipped_extract = tmp_path / "clipped_extract"
    with ZipFile(clipped_zip, "r") as zf:
        zf.extractall(clipped_extract)
    clipped_gdf = gpd.read_file(clipped_extract / "artifact.shp")
    bounds = clipped_gdf.total_bounds.tolist()
    assert bounds == [1.0, 1.0, 2.0, 2.0]
    assert latest.artifact_reuse is not None
    assert latest.artifact_reuse.reused is True
    assert latest.artifact_reuse.artifact_id == "artifact-clip-source"
    assert latest.artifact_reuse.freshness_status == "clip_reused"
    audit_events = service.get_audit_events(status.run_id)
    reuse_event = next(event for event in audit_events if event.kind == "artifact_reuse_applied")
    assert reuse_event.details["reuse_mode"] == "clip"
    assert reuse_event.details["source_artifact_id"] == "artifact-clip-source"


def test_agent_run_service_falls_back_to_fresh_execution_when_clip_reuse_materialization_fails(
    tmp_path: Path, monkeypatch
) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fresh-fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp, fused_shp]:
        path.write_text("dummy", encoding="utf-8")
    artifact_zip.write_bytes(b"zip")

    # Deliberately lie in the registry bbox so candidate selection passes but clipping fails.
    reusable_created_at = _iso_now_minus(hours=1)
    source_artifact = _write_polygon_bundle_zip(
        tmp_path / "artifact-fallback-source.zip",
        [box(0, 0, 1, 1)],
        crs="EPSG:32643",
    )
    service.artifact_registry.register(
        ArtifactRecord(
            artifact_id="artifact-fallback-source",
            artifact_path=str(source_artifact),
            job_type="building",
            disaster_type="flood",
            created_at=reusable_created_at,
            output_fields=[],
            bbox=(0.0, 0.0, 4.0, 4.0),
            output_data_type="dt.building.fused",
            target_crs="EPSG:32643",
            meta={"note": "fallback"},
        )
    )

    plan = _build_plan(workflow_id="wf_fallback", revision=1)
    plan.context["retrieval"]["reusable_artifacts"] = [
        {
            "artifact_id": "artifact-fallback-source",
            "artifact_path": str(source_artifact),
            "created_at": reusable_created_at,
            "bbox": [0.0, 0.0, 4.0, 4.0],
        }
    ]

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    execute_calls = {"count": 0}

    def fake_execute_plan(**_kwargs):
        execute_calls["count"] += 1
        return fused_shp

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.disaster_event,
                content="building",
                disaster_type="flood",
                spatial_extent="bbox(3,3,4,4)",
            ),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert execute_calls["count"] == 1
    assert latest.artifact_reuse is not None
    assert latest.artifact_reuse.reused is False
    assert latest.artifact_reuse.freshness_status == "candidate_available"
    audit_events = service.get_audit_events(status.run_id)
    fallback_event = next(event for event in audit_events if event.kind == "artifact_reuse_fallback")
    assert "clip produced no features" in fallback_event.details["error"]


def test_agent_run_service_skips_stale_reuse_candidates_using_job_type_policy(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fresh-road.shp"
    artifact_zip = tmp_path / "road-artifact.zip"
    for path in [osm_shp, ref_shp, fused_shp]:
        path.write_text("dummy", encoding="utf-8")
    artifact_zip.write_bytes(b"zip")

    source_artifact = _write_polygon_bundle_zip(
        tmp_path / "artifact-road-stale.zip",
        [box(0, 0, 1, 1)],
        crs="EPSG:32643",
    )
    service.artifact_registry.register(
        ArtifactRecord(
            artifact_id="artifact-road-stale",
            artifact_path=str(source_artifact),
            job_type="road",
            disaster_type="flood",
            created_at="2026-04-07T00:00:00+00:00",
            output_fields=["geometry", "osm_id"],
            bbox=(0.0, 0.0, 1.0, 1.0),
            output_data_type="dt.road.fused",
            target_crs="EPSG:32643",
            meta={"note": "should be too old for road reuse"},
        )
    )

    plan = _build_plan(workflow_id="wf_road_stale", revision=1, algorithm_id="algo.fusion.road.v1")
    plan.tasks[0].output.data_type_id = "dt.road.fused"
    plan.context["retrieval"]["reusable_artifacts"] = [
        {
            "artifact_id": "artifact-road-stale",
            "artifact_path": str(source_artifact),
            "created_at": "2026-04-07T00:00:00+00:00",
            "bbox": [0.0, 0.0, 1.0, 1.0],
            "output_data_type": "dt.road.fused",
            "target_crs": "EPSG:32643",
        }
    ]

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    execute_calls = {"count": 0}

    def fake_execute_plan(**_kwargs):
        execute_calls["count"] += 1
        return fused_shp

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.road,
            trigger=RunTrigger(
                type=RunTriggerType.disaster_event,
                content="road",
                disaster_type="flood",
                spatial_extent="bbox(0,0,1,1)",
            ),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert execute_calls["count"] == 1
    assert latest.artifact_reuse is not None
    assert latest.artifact_reuse.reused is False
    assert latest.artifact_reuse.freshness_status == "candidate_available"
    audit_events = service.get_audit_events(status.run_id)
    assert not any(event.kind == "artifact_reuse_applied" for event in audit_events)


def test_agent_run_service_skips_reuse_candidates_with_unsafe_crs(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fresh-crs.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp, fused_shp]:
        path.write_text("dummy", encoding="utf-8")
    artifact_zip.write_bytes(b"zip")

    reusable_created_at = _iso_now_minus(hours=1)
    source_artifact = _write_polygon_bundle_zip(tmp_path / "artifact-crs-mismatch.zip", [box(0, 0, 1, 1)])
    service.artifact_registry.register(
        ArtifactRecord(
            artifact_id="artifact-crs-mismatch",
            artifact_path=str(source_artifact),
            job_type="building",
            disaster_type="flood",
            created_at=reusable_created_at,
            output_fields=["geometry", "confidence"],
            bbox=(0.0, 0.0, 1.0, 1.0),
            output_data_type="dt.building.fused",
            target_crs="EPSG:4326",
            meta={"note": "unsafe target CRS mismatch"},
        )
    )

    plan = _build_plan(workflow_id="wf_crs_mismatch", revision=1)
    plan.context["retrieval"]["reusable_artifacts"] = [
        {
            "artifact_id": "artifact-crs-mismatch",
            "artifact_path": str(source_artifact),
            "created_at": reusable_created_at,
            "bbox": [0.0, 0.0, 1.0, 1.0],
            "output_data_type": "dt.building.fused",
            "target_crs": "EPSG:4326",
        }
    ]

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    execute_calls = {"count": 0}

    def fake_execute_plan(**_kwargs):
        execute_calls["count"] += 1
        return fused_shp

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(
                type=RunTriggerType.disaster_event,
                content="building",
                disaster_type="flood",
                spatial_extent="bbox(0,0,1,1)",
            ),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert execute_calls["count"] == 1
    assert latest.artifact_reuse is not None
    assert latest.artifact_reuse.reused is False
    assert latest.artifact_reuse.freshness_status == "candidate_available"
    audit_events = service.get_audit_events(status.run_id)
    assert not any(event.kind == "artifact_reuse_applied" for event in audit_events)


def test_saved_plan_contains_bound_effective_parameters(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    initial_plan = _build_plan(workflow_id="wf_initial", revision=1)
    initial_plan.tasks[0].input.parameters = {
        "match_similarity_threshold": 0.52,
        "one_to_one_min_overlap_similarity": 0.31,
    }

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: tmp_path / "osm.shp")
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: initial_plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.executor, "execute_plan", lambda **_kwargs: tmp_path / "fused.shp")
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: tmp_path / "artifact.zip")

    (tmp_path / "osm.shp").write_text("x", encoding="utf-8")
    (tmp_path / "ref.shp").write_text("x", encoding="utf-8")
    (tmp_path / "fused.shp").write_text("x", encoding="utf-8")
    (tmp_path / "artifact.zip").write_bytes(b"zip")

    status = service.create_run(
        request=RunCreateRequest(
            job_type=JobType.building,
            trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
            target_crs="EPSG:32643",
            field_mapping={},
            debug=False,
        ),
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(tmp_path / "osm.zip"),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(tmp_path / "ref.zip"),
    )

    saved = service.get_plan(status.run_id)
    assert saved is not None
    assert saved.tasks[0].input.parameters["match_similarity_threshold"] == 0.52
    assert saved.tasks[0].input.parameters["one_to_one_min_overlap_similarity"] == 0.31
    audit_events = service.get_audit_events(status.run_id)
    plan_created = next(event for event in audit_events if event.kind == "plan_created")
    assert plan_created.details["effective_parameters"]["1"]["match_similarity_threshold"] == 0.52
    assert plan_created.details["effective_parameters"]["1"]["one_to_one_min_overlap_similarity"] == 0.31


def test_agent_run_service_replans_after_execution_failure(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    service.max_plan_revisions = 2

    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    fused_shp = tmp_path / "fused.shp"
    artifact_zip = tmp_path / "artifact.zip"
    for path in [osm_shp, ref_shp, fused_shp]:
        path.write_text("dummy", encoding="utf-8")

    initial_plan = _build_plan(workflow_id="wf_initial", revision=1, include_reusable_artifacts=True)
    replanned_plan = _build_plan(workflow_id="wf_replanned", revision=2, algorithm_id="algo.fusion.building.safe")

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: initial_plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)

    replan_calls: list[tuple[int, str]] = []

    def fake_replan(**kwargs):
        replan_calls.append((kwargs["failed_step"], kwargs["error_message"]))
        return replanned_plan.model_copy(deep=True)

    monkeypatch.setattr(service.planner, "replan_from_error", fake_replan)

    execute_calls = {"count": 0}

    def fake_execute_plan(*, plan, context, repair_records, **_kwargs):
        execute_calls["count"] += 1
        if execute_calls["count"] == 1:
            repair_records.extend(
                [
                    RepairRecord(
                        attempt_no=1,
                        strategy="alternative_source",
                        step=1,
                        message="Primary execution failed",
                        success=False,
                        timestamp="2026-04-02T00:00:00+00:00",
                        reason_code="primary_execution_failed",
                        from_algorithm="algo.fusion.building.v1",
                    ),
                    RepairRecord(
                        attempt_no=2,
                        strategy="alternative_algorithm",
                        step=1,
                        message="Alternative algorithm failed",
                        success=False,
                        timestamp="2026-04-02T00:00:01+00:00",
                        reason_code="alternative_algorithm_failed",
                        from_algorithm="algo.fusion.building.v1",
                        to_algorithm="algo.fusion.building.safe",
                    ),
                    RepairRecord(
                        attempt_no=3,
                        strategy="transform_insert",
                        step=1,
                        message="No transform path found.",
                        success=False,
                        timestamp="2026-04-02T00:00:02+00:00",
                        reason_code="transform_path_missing",
                        from_algorithm="algo.fusion.building.v1",
                    ),
                ]
            )
            raise RuntimeError("exhausted repairs")
        return fused_shp

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)
    monkeypatch.setattr("services.agent_run_service.zip_shapefile_bundle", lambda *_args, **_kwargs: artifact_zip)
    artifact_zip.write_bytes(b"zip")

    phase_history: list[RunPhase] = []
    original_update_status = service._update_status

    def tracking_update_status(*args, **kwargs):
        phase = args[1] if len(args) > 1 else kwargs["phase"]
        phase_history.append(phase)
        return original_update_status(*args, **kwargs)

    monkeypatch.setattr(service, "_update_status", tracking_update_status)

    osm_zip = tmp_path / "osm.zip"
    ref_zip = tmp_path / "ref.zip"
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        target_crs="EPSG:32643",
        field_mapping={},
        debug=False,
    )

    status = service.create_run(
        request=request,
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(osm_zip),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(ref_zip),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.succeeded
    assert latest.plan_revision == 2
    assert RunPhase.healing in phase_history
    assert replan_calls and replan_calls[0][0] == 1
    saved_plan = service.get_plan(status.run_id)
    assert saved_plan is not None
    assert saved_plan.workflow_id == "wf_replanned"
    assert saved_plan.context["plan_revision"] == 2
    replan_decisions = [record for record in latest.decision_records if record.decision_type == "replan_or_fail"]
    assert replan_decisions
    assert replan_decisions[-1].selected_id == "replan"
    assert latest.repair_records[-1].reason_code == "transform_path_missing"
    audit_events = service.get_audit_events(status.run_id)
    assert [event.kind for event in audit_events if event.kind in {"replan_requested", "replan_applied"}] == [
        "replan_requested",
        "replan_applied",
    ]
    assert audit_events[-1].kind == "run_succeeded"
    assert audit_events[-1].plan_revision == 2


def test_agent_run_service_fails_when_replan_limit_is_reached(tmp_path: Path, monkeypatch) -> None:
    service = AgentRunService(base_dir=tmp_path / "runs")
    service.max_plan_revisions = 2

    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    for path in [osm_shp, ref_shp]:
        path.write_text("dummy", encoding="utf-8")

    initial_plan = _build_plan(workflow_id="wf_initial", revision=1)
    replanned_plan = _build_plan(workflow_id="wf_replanned", revision=2, algorithm_id="algo.fusion.building.safe")

    monkeypatch.setattr("services.agent_run_service.validate_zip_has_shapefile", lambda *_args, **_kwargs: osm_shp)
    monkeypatch.setattr(service.planner, "create_plan", lambda **_kwargs: initial_plan.model_copy(deep=True))
    monkeypatch.setattr(service.validator, "validate_and_repair", lambda input_plan: input_plan)
    monkeypatch.setattr(service.planner, "replan_from_error", lambda **_kwargs: replanned_plan.model_copy(deep=True))

    execute_calls = {"count": 0}

    def fake_execute_plan(*, plan, context, repair_records, **_kwargs):
        execute_calls["count"] += 1
        repair_records.append(
            RepairRecord(
                attempt_no=len(repair_records) + 1,
                strategy="alternative_algorithm",
                step=1,
                message=f"Attempt {execute_calls['count']} failed",
                success=False,
                timestamp="2026-04-02T00:00:00+00:00",
                reason_code="alternative_algorithm_failed",
                from_algorithm=plan.tasks[0].algorithm_id,
                to_algorithm="algo.fusion.building.safe",
            )
        )
        raise RuntimeError(f"still failing #{execute_calls['count']}")

    monkeypatch.setattr(service.executor, "execute_plan", fake_execute_plan)

    phase_history: list[RunPhase] = []
    original_update_status = service._update_status

    def tracking_update_status(*args, **kwargs):
        phase = args[1] if len(args) > 1 else kwargs["phase"]
        phase_history.append(phase)
        return original_update_status(*args, **kwargs)

    monkeypatch.setattr(service, "_update_status", tracking_update_status)

    osm_zip = tmp_path / "osm.zip"
    ref_zip = tmp_path / "ref.zip"
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        target_crs="EPSG:32643",
        field_mapping={},
        debug=False,
    )

    status = service.create_run(
        request=request,
        osm_zip_name="osm.zip",
        osm_zip_bytes=_write_dummy_zip(osm_zip),
        ref_zip_name="ref.zip",
        ref_zip_bytes=_write_dummy_zip(ref_zip),
    )

    latest = service.get_run(status.run_id)
    assert latest is not None
    assert latest.phase == RunPhase.failed
    assert latest.plan_revision == 2
    assert RunPhase.healing in phase_history
    assert "max plan revisions (2)" in (latest.error or "")
    assert "max plan revisions (2)" in (latest.failure_summary or "")
    saved_plan = service.get_plan(status.run_id)
    assert saved_plan is not None
    assert saved_plan.workflow_id == "wf_replanned"
    assert saved_plan.context["plan_revision"] == 2
    replan_decisions = [record for record in latest.decision_records if record.decision_type == "replan_or_fail"]
    assert replan_decisions
    assert replan_decisions[-1].selected_id == "fail"
    assert latest.artifact_reuse is not None
    assert latest.artifact_reuse.reused is False
    assert latest.artifact_reuse.freshness_status == "not_available"
    audit_events = service.get_audit_events(status.run_id)
    assert any(event.kind == "replan_requested" for event in audit_events)
    assert any(event.kind == "replan_rejected" for event in audit_events)
    assert audit_events[-1].kind == "run_failed"
    assert audit_events[-1].details["error"] == latest.error


def test_update_status_loads_run_from_disk_when_worker_process_is_fresh(tmp_path: Path) -> None:
    base_dir = tmp_path / "runs"
    run_status = RunStatus(
        run_id="run-from-disk",
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        phase=RunPhase.queued,
        progress=0,
        target_crs="EPSG:32643",
        debug=False,
        error=None,
        log_path=str(base_dir / "run-from-disk" / "logs" / "run.log"),
        plan_path=None,
        validation_path=None,
        artifact=None,
        repair_records=[],
        current_step=None,
        attempt_no=0,
        healing_summary={},
        failure_summary=None,
        plan_revision=0,
        created_at="2026-04-02T00:00:00+00:00",
        started_at=None,
        finished_at=None,
    )

    writer = AgentRunService(base_dir=base_dir)
    writer._persist_status(run_status)

    worker_side = AgentRunService(base_dir=base_dir)
    worker_side._runs.clear()

    worker_side._update_status(
        "run-from-disk",
        RunPhase.planning,
        progress=5,
        started_at="2026-04-02T00:00:01+00:00",
    )

    updated = worker_side.get_run("run-from-disk")
    assert updated is not None
    assert updated.phase == RunPhase.planning
    assert updated.progress == 5
    assert updated.started_at == "2026-04-02T00:00:01+00:00"


def test_get_run_refreshes_stale_cached_status_from_disk(tmp_path: Path) -> None:
    base_dir = tmp_path / "runs"

    api_side = AgentRunService(base_dir=base_dir)
    worker_side = AgentRunService(base_dir=base_dir)

    run_status = RunStatus(
        run_id="shared-run",
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        phase=RunPhase.queued,
        progress=0,
        target_crs="EPSG:32643",
        debug=False,
        error=None,
        log_path=str(base_dir / "shared-run" / "logs" / "run.log"),
        plan_path=None,
        validation_path=None,
        artifact=None,
        repair_records=[],
        current_step=None,
        attempt_no=0,
        healing_summary={},
        failure_summary=None,
        plan_revision=0,
        created_at="2026-04-02T00:00:00+00:00",
        started_at=None,
        finished_at=None,
    )

    api_side._persist_status(run_status)
    api_side._runs["shared-run"] = run_status

    worker_side._update_status(
        "shared-run",
        RunPhase.failed,
        progress=100,
        error="RuntimeError: boom",
        finished_at="2026-04-02T00:00:02+00:00",
        failure_summary="RuntimeError: boom",
    )

    refreshed = api_side.get_run("shared-run")
    assert refreshed is not None
    assert refreshed.phase == RunPhase.failed
    assert refreshed.error == "RuntimeError: boom"
    assert refreshed.finished_at == "2026-04-02T00:00:02+00:00"
