from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from schemas.agent import RepairRecord, RunCreateRequest, RunTrigger, RunTriggerType, WorkflowPlan
from schemas.fusion import JobType
from worker.celery_app import celery_app


LOGGER = logging.getLogger("geofusion.worker")


def _load_scheduled_specs() -> List[Dict[str, Any]]:
    raw = os.getenv("GEOFUSION_SCHEDULED_RUNS", "").strip()
    if not raw:
        return []
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("GEOFUSION_SCHEDULED_RUNS must be a JSON array.")
    return [item for item in payload if isinstance(item, dict)]


@celery_app.task(name="geofusion.plan_run")
def plan_run_task(run_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
    from services.agent_run_service import agent_run_service

    run_request = RunCreateRequest.model_validate(request)
    plan = agent_run_service.run_planning_stage(run_id=run_id, request=run_request)
    return plan.model_dump(mode="json")


@celery_app.task(name="geofusion.validate_run")
def validate_run_task(run_id: str, plan: Dict[str, Any]) -> Dict[str, Any]:
    from services.agent_run_service import agent_run_service

    workflow_plan = WorkflowPlan.model_validate(plan)
    validated = agent_run_service.run_validation_stage(run_id=run_id, plan=workflow_plan)
    return validated.model_dump(mode="json")


@celery_app.task(name="geofusion.execute_plan")
def execute_plan_task(
    run_id: str,
    request: Dict[str, Any],
    plan: Dict[str, Any],
    osm_zip_path: str,
    ref_zip_path: str,
    intermediate_dir: str,
    output_dir: str,
) -> Dict[str, Any]:
    from services.agent_run_service import agent_run_service

    run_request = RunCreateRequest.model_validate(request)
    workflow_plan = WorkflowPlan.model_validate(plan)
    fused_shp, repair_records = agent_run_service.run_execution_stage(
        run_id=run_id,
        request=run_request,
        plan=workflow_plan,
        osm_zip_path=Path(osm_zip_path),
        ref_zip_path=Path(ref_zip_path),
        intermediate_dir=Path(intermediate_dir),
        output_dir=Path(output_dir),
    )
    return {
        "fused_shp_path": str(fused_shp),
        "repair_records": [record.model_dump(mode="json") for record in repair_records],
    }


@celery_app.task(name="geofusion.writeback_run")
def writeback_run_task(
    run_id: str,
    request: Dict[str, Any],
    plan: Dict[str, Any],
    fused_shp_path: str,
    repair_records: List[Dict[str, Any]],
    output_dir: str,
) -> Dict[str, Any]:
    from services.agent_run_service import agent_run_service

    run_request = RunCreateRequest.model_validate(request)
    workflow_plan = WorkflowPlan.model_validate(plan)
    repairs = [RepairRecord.model_validate(record) for record in repair_records]
    artifact = agent_run_service.run_writeback_stage(
        run_id=run_id,
        request=run_request,
        plan=workflow_plan,
        fused_shp=Path(fused_shp_path),
        repair_records=repairs,
        output_dir=Path(output_dir),
    )
    return artifact.model_dump(mode="json")


@celery_app.task(name="geofusion.execute_run")
def execute_run_task(
    run_id: str,
    request: Dict[str, Any],
    osm_zip_path: str,
    ref_zip_path: str,
    intermediate_dir: str,
    output_dir: str,
    log_dir: str,
) -> None:
    from services.agent_run_service import agent_run_service

    run_request = RunCreateRequest.model_validate(request)
    agent_run_service.execute_run(
        run_id=run_id,
        request=run_request,
        osm_zip_path=Path(osm_zip_path),
        ref_zip_path=Path(ref_zip_path),
        intermediate_dir=Path(intermediate_dir),
        output_dir=Path(output_dir),
        log_dir=Path(log_dir),
    )


@celery_app.task(name="geofusion.scheduled_tick")
def scheduled_tick() -> Dict[str, Any]:
    from services.agent_run_service import agent_run_service

    run_ids: List[str] = []
    errors: List[str] = []
    scheduled_specs = _load_scheduled_specs()
    for index, spec in enumerate(scheduled_specs, start=1):
        if spec.get("enabled", True) is False:
            continue
        try:
            osm_zip_path = Path(str(spec["osm_zip_path"]))
            ref_zip_path = Path(str(spec["ref_zip_path"]))
            request = RunCreateRequest(
                job_type=JobType(spec["job_type"]),
                trigger=RunTrigger(
                    type=RunTriggerType.scheduled,
                    content=str(spec.get("trigger_content", f"scheduled-{index}")),
                    disaster_type=spec.get("disaster_type"),
                    spatial_extent=spec.get("spatial_extent"),
                    temporal_start=spec.get("temporal_start"),
                    temporal_end=spec.get("temporal_end"),
                ),
                target_crs=str(spec.get("target_crs", "EPSG:32643")),
                field_mapping=dict(spec.get("field_mapping", {})),
                debug=bool(spec.get("debug", False)),
            )
            created = agent_run_service.create_run(
                request=request,
                osm_zip_name=osm_zip_path.name,
                osm_zip_bytes=osm_zip_path.read_bytes(),
                ref_zip_name=ref_zip_path.name,
                ref_zip_bytes=ref_zip_path.read_bytes(),
            )
            run_ids.append(created.run_id)
        except Exception as exc:  # noqa: BLE001
            message = f"scheduled_spec_{index}: {type(exc).__name__}: {exc}"
            LOGGER.warning(message)
            errors.append(message)

    return {
        "configured": len(scheduled_specs),
        "created": len(run_ids),
        "run_ids": run_ids,
        "errors": errors,
    }
