from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List

from schemas.agent import RepairRecord, RunCreateRequest, RunInputStrategy, RunTrigger, RunTriggerType, WorkflowPlan
from schemas.fusion import JobType
from schemas.settings import EffectiveLLMSettings
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


def _as_bool_env(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _as_int_env(name: str, default: str) -> int:
    try:
        return int(os.getenv(name, default).strip())
    except ValueError:
        return int(default)


def scheduled_tick_control_state() -> Dict[str, Any]:
    specs = _load_scheduled_specs()
    enabled_specs = sum(1 for spec in specs if spec.get("enabled", True) is not False)
    return {
        "task": "geofusion.scheduled_tick",
        "configured_specs": len(specs),
        "enabled_specs": enabled_specs,
    }


def recovery_tick_control_state() -> Dict[str, Any]:
    return {
        "task": "geofusion.recovery_tick",
        "enabled": _as_bool_env("GEOFUSION_RECOVERY_ENABLED", "1"),
        "stale_after_seconds": _as_int_env("GEOFUSION_RECOVERY_STALE_SECONDS", "300"),
        "limit": _as_int_env("GEOFUSION_RECOVERY_LIMIT", "20"),
        "lease_seconds": _as_int_env("GEOFUSION_RECOVERY_LEASE_SECONDS", "300"),
    }


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
    osm_zip_path: str | None,
    ref_zip_path: str | None,
    intermediate_dir: str,
    output_dir: str,
    log_dir: str,
    runtime_snapshot_id: str | None = None,
    runtime_settings: Dict[str, Any] | None = None,
) -> None:
    from services.agent_run_service import agent_run_service

    run_request = RunCreateRequest.model_validate(request)
    agent_run_service.execute_run(
        run_id=run_id,
        request=run_request,
        osm_zip_path=Path(osm_zip_path) if osm_zip_path else None,
        ref_zip_path=Path(ref_zip_path) if ref_zip_path else None,
        intermediate_dir=Path(intermediate_dir),
        output_dir=Path(output_dir),
        log_dir=Path(log_dir),
        runtime_snapshot_id=runtime_snapshot_id,
        runtime_settings=EffectiveLLMSettings.model_validate(runtime_settings) if runtime_settings is not None else None,
    )


@celery_app.task(name="geofusion.scheduled_tick")
def scheduled_tick() -> Dict[str, Any]:
    from services.agent_run_service import agent_run_service

    run_ids: List[str] = []
    errors: List[str] = []
    spec_results: List[Dict[str, Any]] = []
    scheduled_specs = _load_scheduled_specs()
    for index, spec in enumerate(scheduled_specs, start=1):
        if spec.get("enabled", True) is False:
            spec_results.append({"index": index, "status": "skipped_disabled"})
            continue
        input_strategy = RunInputStrategy(str(spec.get("input_strategy", RunInputStrategy.uploaded.value)))
        try:
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
                input_strategy=input_strategy,
                preferred_pattern_id=spec.get("preferred_pattern_id"),
            )
            if input_strategy == RunInputStrategy.uploaded:
                osm_zip_path = Path(str(spec["osm_zip_path"]))
                ref_zip_path = Path(str(spec["ref_zip_path"]))
                created = agent_run_service.create_run(
                    request=request,
                    osm_zip_name=osm_zip_path.name,
                    osm_zip_bytes=osm_zip_path.read_bytes(),
                    ref_zip_name=ref_zip_path.name,
                    ref_zip_bytes=ref_zip_path.read_bytes(),
                )
            else:
                created = agent_run_service.create_run(
                    request=request,
                    osm_zip_name=None,
                    osm_zip_bytes=None,
                    ref_zip_name=None,
                    ref_zip_bytes=None,
                )
            run_ids.append(created.run_id)
            spec_results.append(
                {
                    "index": index,
                    "status": "created",
                    "run_id": created.run_id,
                    "input_strategy": input_strategy.value,
                }
            )
        except Exception as exc:  # noqa: BLE001
            message = f"scheduled_spec_{index}: {type(exc).__name__}: {exc}"
            LOGGER.warning(message)
            errors.append(message)
            spec_results.append(
                {
                    "index": index,
                    "status": "error",
                    "input_strategy": str(spec.get("input_strategy", RunInputStrategy.uploaded.value)),
                    "error": message,
                }
            )

    return {
        "configured": len(scheduled_specs),
        "created": len(run_ids),
        "run_ids": run_ids,
        "errors": errors,
        "spec_results": spec_results,
    }


@celery_app.task(name="geofusion.recover_run")
def recover_run_task(run_id: str, recovery_action: str) -> Dict[str, Any]:
    from services.agent_run_service import agent_run_service
    from services.run_recovery_executor import RunRecoveryExecutor

    executor = RunRecoveryExecutor(
        runs_root=agent_run_service.base_dir,
        agent_run_service=agent_run_service,
        lease_seconds=_as_int_env("GEOFUSION_RECOVERY_LEASE_SECONDS", "300"),
    )
    return executor.recover_run(run_id=run_id, recovery_action=recovery_action)


@celery_app.task(name="geofusion.recovery_tick")
def recovery_tick() -> Dict[str, Any]:
    if not _as_bool_env("GEOFUSION_RECOVERY_ENABLED", "1"):
        return {"enabled": False, "reason": "disabled"}

    from services.agent_run_service import agent_run_service
    from services.run_recovery_executor import RunRecoveryExecutor

    executor = RunRecoveryExecutor(
        runs_root=agent_run_service.base_dir,
        agent_run_service=agent_run_service,
        lease_seconds=_as_int_env("GEOFUSION_RECOVERY_LEASE_SECONDS", "300"),
    )
    result = executor.recover_stale_runs(
        stale_after_seconds=_as_int_env("GEOFUSION_RECOVERY_STALE_SECONDS", "300"),
        limit=_as_int_env("GEOFUSION_RECOVERY_LIMIT", "20"),
    )
    return {"enabled": True, **result}
