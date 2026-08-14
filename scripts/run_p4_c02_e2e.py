from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import RunCreateRequest, RunInputStrategy, RunTrigger, RunTriggerType, WorkflowPlan
from schemas.contract_experiment import ContractExperimentManifest, ExperimentStageDeclaration
from schemas.task_kind import TaskKind, task_kind_to_job_type
from scripts.freeze_p4_c02_protocol import PROTOCOL_ID, STAGE_TASK_KINDS, verify_p4_c02_freeze
from services.contract_experiment_service import load_experiment_manifest, prepare_stage_sources, sha256_file


def preflight_p4_c02_runner(freeze_root: Path) -> dict[str, Any]:
    freeze_root = freeze_root.resolve()
    audit = verify_p4_c02_freeze(freeze_root)
    protocol = _read_json(freeze_root / "protocol.json")
    config = _read_json(freeze_root / "execution_config.json")
    stage_plans = _read_json(freeze_root / "stage_plans.json")
    evidence_root = Path(config["evidence_root"])
    runner_contract = protocol.get("runner_contract") or {}
    expected_hashes = protocol.get("frozen_artifact_hashes", {}).get("stage_plans", {})
    checks = {
        "freeze_audit": audit["passed"] is True,
        "protocol_version": protocol.get("protocol_id") == PROTOCOL_ID,
        "execution_ready": protocol.get("execution_ready") is True
        and protocol.get("execution_blockers") == [],
        "runner_mode": runner_contract.get("stage_execution") == "three_independent_task_runs",
        "frozen_validation_mode": runner_contract.get("execution_validation_gate")
        == "workflow_validator_enforce"
        and runner_contract.get("frozen_plan_persistence") == "canonical_no_derived_fields",
        "stage_order": config.get("stage_order") == list(STAGE_TASK_KINDS),
        "stage_plan_hashes": set(stage_plans) == set(STAGE_TASK_KINDS)
        and all(
            _workflow_plan_semantic_hash(WorkflowPlan.model_validate(stage_plans[kind]))
            == expected_hashes.get(kind)
            for kind in STAGE_TASK_KINDS
        ),
        "zero_llm_calls": config["runtime"]["llm_calls"] == 0
        and config["budget"]["max_llm_calls"] == 0,
        "local_only": config["runtime"]["local_only"] is True
        and config["budget"]["max_provider_network_calls"] == 0,
        "fallback_forbidden": config["runtime"]["fallback"] == "forbidden"
        and config["runtime"]["automatic_retries"] == 0,
        "artifact_reuse_disabled": config["runtime"]["artifact_reuse"] is False,
        "gap_contract": config.get("gap_declaration")
        == {
            "building": {"materialize": False, "reason_code": "DELIVERY_STATE_GAP", "status": "gap"},
            "poi": {"materialize": False, "reason_code": "DELIVERY_STATE_GAP", "status": "gap"},
        },
        "evidence_root_empty": not evidence_root.exists() or not any(evidence_root.iterdir()),
    }
    return {
        "report_type": "p4_c02_runner_preflight",
        "protocol_id": protocol.get("protocol_id"),
        "freeze_root": str(freeze_root),
        "evidence_root": str(evidence_root),
        "checks": checks,
        "passed": all(checks.values()),
        "provider_calls_made": 0,
        "llm_calls_made": 0,
        "fusion_runs_started": 0,
    }


def execute_p4_c02_runner(freeze_root: Path) -> dict[str, Any]:
    freeze_root = freeze_root.resolve()
    preflight = preflight_p4_c02_runner(freeze_root)
    if not preflight["passed"]:
        raise RuntimeError(f"P4 C02 preflight failed: {preflight['checks']}")

    protocol = _read_json(freeze_root / "protocol.json")
    config = _read_json(freeze_root / "execution_config.json")
    inventory = _read_json(freeze_root / "asset_inventory.json")
    stage_payloads = _read_json(freeze_root / "stage_plans.json")
    stage_plans = {
        kind: WorkflowPlan.model_validate(stage_payloads[kind]) for kind in STAGE_TASK_KINDS
    }
    evidence_root = Path(config["evidence_root"])
    if evidence_root.exists():
        raise FileExistsError(f"Evidence root already exists: {evidence_root}")
    evidence_root.mkdir(parents=True)
    shutil.copytree(freeze_root, evidence_root / "protocol_freeze")
    _write_json(evidence_root / "preflight.json", preflight)

    runtime_root = evidence_root / "runtime"
    data_root = runtime_root / "data_repository"
    download_root = runtime_root / "downloads"
    runs_root = runtime_root / "runs"
    for path in (data_root, download_root, runs_root):
        path.mkdir(parents=True, exist_ok=True)

    asset_manifest_ref = inventory["inputs"]["case_manifest"]
    asset_manifest_path = Path(asset_manifest_ref["path"])
    if _prefixed_file_hash(asset_manifest_path) != asset_manifest_ref["sha256"]:
        raise RuntimeError("C02 asset manifest hash drifted after protocol freeze")
    asset_manifest = load_experiment_manifest(asset_manifest_path)
    active_source_ids = {
        source_id for stage in config["stages"] for source_id in stage["active_source_ids"]
    }
    selected_sources = [source for source in asset_manifest.sources if source.source_id in active_source_ids]
    if {source.source_id for source in selected_sources} != active_source_ids:
        raise RuntimeError("C02 staging manifest does not contain every frozen source")
    staging_manifest = ContractExperimentManifest(
        schema_version="1.0.0",
        experiment_id=config["case_identity"]["run_id"],
        title="P4 C02 frozen water and road stage inputs",
        data_boundary={"real_external_data": True, "asset_reuse_only": True},
        runtime={"local_only": True},
        sources=selected_sources,
        cases=[],
        metric_definition_path="docs/thesis/contract_case_metrics_v1.json",
    )

    stage_records: list[dict[str, Any]] = []
    environment = {
        "GEOFUSION_LOCAL_ONLY": "1",
        "GEOFUSION_KG_BACKEND": "memory",
        "GEOFUSION_DISABLE_ARTIFACT_REUSE": "1",
        "GEOFUSION_CELERY_EAGER": "1",
        "GEOFUSION_MAX_PLAN_REVISIONS": "1",
        "GEOFUSION_VALIDATOR_MODE": "enforce",
        "GEOFUSION_INPUT_ACQUISITION_TIMEOUT_SECONDS": str(
            config["budget"]["max_wall_seconds_per_stage"]
        ),
    }
    with _temporary_environment(environment):
        from services.agent_run_service import AgentRunService

        service = AgentRunService(
            base_dir=runs_root,
            max_workers=1,
            kg_repo=InMemoryKGRepository(experience_policy="pinned_snapshot"),
            data_repository_root=data_root,
            download_root=download_root,
        )
        try:
            for stage in config["stages"]:
                stage_id = stage["stage_id"]
                plan = stage_plans[stage_id]
                expected_plan_hash = protocol["frozen_artifact_hashes"]["stage_plans"][stage_id]
                stage_dir = evidence_root / "stages" / stage_id
                stage_dir.mkdir(parents=True, exist_ok=True)
                prepared = prepare_stage_sources(
                    manifest=staging_manifest,
                    stage=ExperimentStageDeclaration(
                        stage_id=stage_id,
                        action="create",
                        active_source_ids=stage["active_source_ids"],
                    ),
                    data_root=data_root,
                    evidence_dir=stage_dir,
                )
                request = _stage_request(stage_id, config)
                status = service.create_run(
                    request=request,
                    osm_zip_name=None,
                    osm_zip_bytes=None,
                    ref_zip_name=None,
                    ref_zip_bytes=None,
                    frozen_plan=plan,
                    frozen_plan_sha256=expected_plan_hash,
                )
                current = service.get_run(status.run_id) or status
                events = [event.model_dump(mode="json") for event in service.get_audit_events(status.run_id)]
                record = _build_stage_record(
                    stage=stage,
                    status=current.model_dump(mode="json"),
                    events=events,
                    prepared=prepared,
                    runs_root=runs_root,
                    expected_plan_hash=expected_plan_hash,
                )
                _write_json(stage_dir / "stage_record.json", record)
                stage_records.append(record)
                if not record["runtime_succeeded"]:
                    _write_failure(evidence_root, protocol, config, stage_records, record)
                    raise RuntimeError(f"P4 C02 stage failed: {stage_id} run_id={status.run_id}")
        finally:
            service.shutdown()

    evaluation = _evaluate_stages(
        records=stage_records,
        config=config,
        selected_hash=protocol["frozen_artifact_hashes"]["selected_plan"],
        resolved_hash=protocol["frozen_artifact_hashes"]["resolved_plan"],
    )
    _write_json(evidence_root / "gap_declaration.json", config["gap_declaration"])
    _write_json(evidence_root / "selected_resolved_executed_evaluated.json", evaluation)
    result = {
        "protocol_id": protocol["protocol_id"],
        "case_identity": config["case_identity"],
        "stage_records": stage_records,
        "gap_declaration": config["gap_declaration"],
        "evaluation": evaluation,
        "passed": evaluation["passed"],
        "claim_boundary": protocol["evaluation_boundary"]["claim_boundary"],
    }
    _write_json(evidence_root / "experiment_result.json", result)
    return result


def _stage_request(stage_id: str, config: dict[str, Any]) -> RunCreateRequest:
    task_kind = TaskKind(stage_id)
    return RunCreateRequest(
        job_type=task_kind_to_job_type(task_kind),
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content=f"C02 frozen flood {stage_id} execution",
            disaster_type="flood",
            spatial_extent=config["aoi"]["spatial_extent"],
        ),
        target_crs=config["aoi"]["target_crs"],
        input_strategy=RunInputStrategy.task_driven_auto,
        debug=False,
    )


def _build_stage_record(
    *,
    stage: dict[str, Any],
    status: dict[str, Any],
    events: list[dict[str, Any]],
    prepared: dict[str, Any],
    runs_root: Path,
    expected_plan_hash: str,
) -> dict[str, Any]:
    run_id = status["run_id"]
    run_dir = runs_root / run_id
    injected_path = run_dir / "frozen_plan_input.json"
    injected = _read_json(injected_path)
    artifact = status.get("artifact") or {}
    artifact_path = Path(str(artifact.get("path") or ""))
    injected_events = [event for event in events if event.get("kind") == "frozen_plan_injected"]
    component_coverage = _last_event_detail(events, "task_inputs_resolved", "component_coverage") or {}
    return {
        "stage_id": stage["stage_id"],
        "task_kind": stage["task_kind"],
        "run_id": run_id,
        "runtime_phase": status["phase"],
        "runtime_error": status.get("error"),
        "runtime_succeeded": status["phase"] == "succeeded" and artifact_path.is_file(),
        "planning_telemetry": status.get("planning_telemetry") or {},
        "prepared_inputs": prepared,
        "injected_plan_sha256": _workflow_plan_semantic_hash(WorkflowPlan.model_validate(injected)),
        "expected_plan_sha256": expected_plan_hash,
        "frozen_plan_injected_event_count": len(injected_events),
        "component_coverage": component_coverage,
        "source_materialization": _materialization_evidence(events),
        "source_semantic_contract": _semantic_contract_evidence(status),
        "quality_evaluation": _quality_evidence(events),
        "artifact_path": str(artifact_path) if artifact_path.is_file() else None,
        "artifact_sha256": sha256_file(artifact_path) if artifact_path.is_file() else None,
        "output_artifacts": _output_artifacts(run_dir / "output"),
        "events": events,
    }


def _evaluate_stages(
    *,
    records: list[dict[str, Any]],
    config: dict[str, Any],
    selected_hash: str,
    resolved_hash: str,
) -> dict[str, Any]:
    expected_order = list(STAGE_TASK_KINDS)
    record_by_stage = {record.get("stage_id"): record for record in records}
    ordered_records = [record_by_stage.get(stage_id) for stage_id in expected_order]
    all_present = all(isinstance(record, dict) for record in ordered_records)
    if not all_present:
        ordered_records = [record for record in ordered_records if isinstance(record, dict)]

    expected_sources = {
        stage["stage_id"]: set(stage["active_source_ids"]) - {config["aoi"]["boundary_source_id"]}
        for stage in config["stages"]
    }
    expected_staged_sources = {
        stage["stage_id"]: set(stage["active_source_ids"]) for stage in config["stages"]
    }
    distinct_runs = len({record.get("run_id") for record in ordered_records}) == len(expected_order)
    checks = {
        "three_stage_records_in_order": all_present
        and [record.get("stage_id") for record in records] == expected_order,
        "three_runs_completed": all_present
        and all(record.get("runtime_succeeded") is True for record in ordered_records),
        "independent_runtime_runs": all_present and distinct_runs,
        "exact_stage_plans_injected": all_present
        and all(
            record.get("injected_plan_sha256") == record.get("expected_plan_sha256")
            and record.get("frozen_plan_injected_event_count") == 1
            for record in ordered_records
        ),
        "frozen_stage_source_sets_prepared": all_present
        and all(
            set((record.get("prepared_inputs") or {}).get("active_source_ids") or [])
            == expected_staged_sources[record["stage_id"]]
            for record in ordered_records
        ),
        "frozen_sources_materialized_non_empty": all_present
        and all(
            all(_component_non_empty(record.get("component_coverage") or {}, source_id)
                for source_id in expected_sources[record["stage_id"]])
            for record in ordered_records
        ),
        "materialization_manifests_recorded": all_present
        and all(
            _materialization_evidence_valid(
                record.get("source_materialization") or {},
                record.get("component_coverage") or {},
            )
            for record in ordered_records
        ),
        "semantic_contracts_valid": all_present
        and all(
            _semantic_contract_valid(
                record.get("source_semantic_contract") or {},
                expected_sources[record["stage_id"]],
            )
            for record in ordered_records
        ),
        "quality_evaluated_and_accepted": all_present
        and all(
            _quality_evaluation_valid(
                record.get("quality_evaluation") or {},
                record.get("component_coverage") or {},
            )
            for record in ordered_records
        )
        and len(
            {(record.get("quality_evaluation") or {}).get("report_sha256") for record in ordered_records}
        )
        == len(expected_order),
        "artifacts_hashed": all_present
        and all(record.get("artifact_sha256") for record in ordered_records),
        "vector_artifacts_recorded": all_present
        and all(any(item["suffix"] == ".gpkg" for item in record.get("output_artifacts") or [])
                for record in ordered_records),
        "no_retry_or_replan_observed": all_present
        and all(
            all(int(event.get("attempt_no") or 0) == 0 for event in record.get("events") or [])
            and not any(event.get("kind") in {"replan_started", "artifact_reused"}
                        for event in record.get("events") or [])
            for record in ordered_records
        ),
        "zero_llm_planning_calls": all_present
        and all(
            (record.get("planning_telemetry") or {}).get("planning_mode")
            == "frozen_workflow_plan_injection"
            and int((record.get("planning_telemetry") or {}).get("llm_calls") or 0) == 0
            for record in ordered_records
        ),
        "building_poi_gap_only": config.get("gap_declaration")
        == {
            "building": {"materialize": False, "reason_code": "DELIVERY_STATE_GAP", "status": "gap"},
            "poi": {"materialize": False, "reason_code": "DELIVERY_STATE_GAP", "status": "gap"},
        }
        and not any(record.get("task_kind") in {"building", "poi"} for record in records),
    }
    return {
        "selected": {
            "source": "formal-c02-llm_full_contract_kg-r1",
            "semantic_sha256": selected_hash,
            "preserved": True,
        },
        "resolved": {
            "semantic_sha256": resolved_hash,
            "stage_order": expected_order,
            "resolution_basis": "frozen_kg_workflow_pattern",
        },
        "executed": {
            "run_ids": [record.get("run_id") for record in ordered_records],
            "artifact_sha256": [record.get("artifact_sha256") for record in ordered_records],
        },
        "evaluated": {
            "quality_report_sha256": [
                (record.get("quality_evaluation") or {}).get("report_sha256")
                for record in ordered_records
            ],
            "gap_declaration": config.get("gap_declaration"),
        },
        "checks": checks,
        "passed": all(checks.values()),
    }


def _write_failure(
    evidence_root: Path,
    protocol: dict[str, Any],
    config: dict[str, Any],
    records: list[dict[str, Any]],
    failed: dict[str, Any],
) -> None:
    _write_json(
        evidence_root / "experiment_failure.json",
        {
            "protocol_id": protocol["protocol_id"],
            "case_identity": config["case_identity"],
            "failed_stage_id": failed["stage_id"],
            "failed_run_id": failed["run_id"],
            "error": failed.get("runtime_error"),
            "runtime_runs_created": len(records),
            "stages_completed": sum(record.get("runtime_succeeded") is True for record in records),
            **_fusion_execution_counts(records),
            "automatic_retry_performed": False,
            "stage_records": records,
        },
    )


def _fusion_execution_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    events = [event for record in records for event in record.get("events") or []]
    return {
        "fusion_algorithm_executions_started": sum(
            event.get("kind") in {"execution_started", "large_area_tile_started"} for event in events
        ),
        "fusion_algorithm_executions_completed": sum(
            event.get("kind") in {"execution_completed", "large_area_tile_completed"} for event in events
        ),
    }


def _last_event_detail(events: list[dict[str, Any]], kind: str, key: str) -> Any:
    for event in reversed(events):
        if event.get("kind") == kind:
            return (event.get("details") or {}).get(key)
    return None


def _materialization_evidence(events: list[dict[str, Any]]) -> dict[str, Any]:
    value = _last_event_detail(events, "task_inputs_resolved", "source_materialization_manifest_path")
    path = Path(str(value or ""))
    if not path.is_file():
        return {"path": str(path) if value else None, "sha256": None, "manifest": None}
    return {"path": str(path), "sha256": sha256_file(path), "manifest": _read_json(path)}


def _semantic_contract_evidence(status: dict[str, Any]) -> dict[str, Any]:
    value = status.get("source_semantic_contract_path")
    path = Path(str(value or ""))
    if not path.is_file():
        return {"path": str(path) if value else None, "sha256": None, "contract": None}
    return {"path": str(path), "sha256": sha256_file(path), "contract": _read_json(path)}


def _quality_evidence(events: list[dict[str, Any]]) -> dict[str, Any]:
    quality_events = [event for event in events if event.get("kind") == "quality_gate_evaluated"]
    if not quality_events:
        return {"event_count": 0, "accepted": None, "report_path": None, "report_sha256": None}
    details = quality_events[-1].get("details") or {}
    path = Path(str(details.get("path") or ""))
    return {
        "event_count": len(quality_events),
        "accepted": details.get("accepted"),
        "policy_id": details.get("policy_id"),
        "report_path": str(path) if path.is_file() else None,
        "report_sha256": sha256_file(path) if path.is_file() else None,
        "component_coverage": details.get("component_coverage"),
    }


def _output_artifacts(output_dir: Path) -> list[dict[str, Any]]:
    paths = sorted(list(output_dir.glob("*.gpkg")) + list(output_dir.glob("*.zip")))
    return [
        {"path": str(path), "suffix": path.suffix.lower(), "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
        for path in paths
        if path.is_file()
    ]


def _component_non_empty(coverage: dict[str, Any], source_id: str) -> bool:
    value = coverage.get(source_id)
    if not isinstance(value, dict) or not value.get("path"):
        return False
    try:
        return int(value.get("feature_count") or 0) > 0
    except (TypeError, ValueError):
        return False


def _materialization_evidence_valid(evidence: dict[str, Any], coverage: dict[str, Any]) -> bool:
    manifest = evidence.get("manifest")
    return bool(evidence.get("sha256")) and isinstance(manifest, dict) and manifest.get("component_coverage") == coverage


def _semantic_contract_valid(evidence: dict[str, Any], expected_source_ids: set[str]) -> bool:
    contract = evidence.get("contract")
    return (
        bool(evidence.get("sha256"))
        and isinstance(contract, dict)
        and (contract.get("validation") or {}).get("valid") is True
        and set(contract.get("component_source_ids") or []) == expected_source_ids
    )


def _quality_evaluation_valid(evidence: dict[str, Any], expected_coverage: dict[str, Any]) -> bool:
    return (
        int(evidence.get("event_count") or 0) >= 1
        and evidence.get("accepted") is True
        and bool(evidence.get("report_path"))
        and bool(evidence.get("report_sha256"))
        and evidence.get("component_coverage") == expected_coverage
    )


@contextmanager
def _temporary_environment(values: dict[str, str]) -> Iterator[None]:
    previous = {key: os.environ.get(key) for key in values}
    os.environ.update(values)
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _workflow_plan_semantic_hash(plan: WorkflowPlan) -> str:
    payload = json.dumps(
        plan.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _prefixed_file_hash(path: Path) -> str:
    return "sha256:" + sha256_file(path)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight or execute the frozen P4 C02 protocol.")
    parser.add_argument("--freeze", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        result = preflight_p4_c02_runner(args.freeze)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["passed"] else 2
    result = execute_p4_c02_runner(args.freeze)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
