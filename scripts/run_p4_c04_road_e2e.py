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
from schemas.fusion import JobType
from scripts.freeze_p4_c04_road_protocol import PROTOCOL_ID, SOURCE_IDS, verify_p4_c04_freeze
from services.contract_experiment_service import load_experiment_manifest, prepare_stage_sources, sha256_file


def preflight_p4_c04_runner(freeze_root: Path) -> dict[str, Any]:
    freeze_root = freeze_root.resolve()
    audit = verify_p4_c04_freeze(freeze_root)
    protocol = _read_json(freeze_root / "protocol.json")
    config = _read_json(freeze_root / "execution_config.json")
    plan = WorkflowPlan.model_validate(_read_json(freeze_root / "workflow_plan.json"))
    evidence_root = Path(config["evidence_root"])
    runner_contract = protocol.get("runner_contract") or {}
    checks = {
        "freeze_audit": audit["passed"] is True,
        "protocol_version": protocol.get("protocol_id") == PROTOCOL_ID,
        "execution_ready": protocol.get("execution_ready") is True
        and protocol.get("execution_blockers") == [],
        "runner_mode": runner_contract.get("stage_execution") == "independent_runs_with_explicit_supersession",
        "frozen_validation_mode": runner_contract.get("execution_validation_gate")
        == "workflow_validator_enforce"
        and runner_contract.get("generic_grounding_probe") == "diagnostic_only"
        and runner_contract.get("frozen_plan_persistence") == "canonical_no_derived_fields",
        "frozen_plan_hash": _workflow_plan_semantic_hash(plan)
        == protocol["frozen_artifact_hashes"]["workflow_plan"],
        "zero_llm_calls": config["runtime"]["llm_calls"] == 0 and config["budget"]["max_llm_calls"] == 0,
        "local_only": config["runtime"]["local_only"] is True
        and config["budget"]["max_provider_network_calls"] == 0,
        "fallback_forbidden": config["runtime"]["fallback"] == "forbidden"
        and config["runtime"]["automatic_retries"] == 0,
        "evidence_root_empty": not evidence_root.exists() or not any(evidence_root.iterdir()),
        "two_stage_contract": [stage["stage_id"] for stage in config["stages"]]
        == ["osm_provisional", "microsoft_arrival"],
    }
    return {
        "report_type": "p4_c04_runner_preflight",
        "freeze_root": str(freeze_root),
        "evidence_root": str(evidence_root),
        "checks": checks,
        "passed": all(checks.values()),
        "provider_calls_made": 0,
        "llm_calls_made": 0,
        "fusion_runs_started": 0,
    }


def execute_p4_c04_runner(freeze_root: Path) -> dict[str, Any]:
    freeze_root = freeze_root.resolve()
    preflight = preflight_p4_c04_runner(freeze_root)
    if not preflight["passed"]:
        raise RuntimeError(f"P4 C04 preflight failed: {preflight['checks']}")
    config = _read_json(freeze_root / "execution_config.json")
    protocol = _read_json(freeze_root / "protocol.json")
    plan = WorkflowPlan.model_validate(_read_json(freeze_root / "workflow_plan.json"))
    expected_plan_hash = protocol["frozen_artifact_hashes"]["workflow_plan"]
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

    asset_manifest_path = Path(protocol["input_evidence"]["asset_manifest"]["path"])
    asset_manifest = load_experiment_manifest(asset_manifest_path)
    selected_sources = [source for source in asset_manifest.sources if source.source_id in SOURCE_IDS]
    staging_manifest = ContractExperimentManifest(
        schema_version="1.0.0",
        experiment_id=config["case_identity"]["run_id"],
        title="P4 C04 frozen road stage inputs",
        data_boundary={"real_external_data": True, "asset_reuse_only": True},
        runtime={"local_only": True},
        sources=selected_sources,
        cases=[],
        metric_definition_path="docs/thesis/contract_case_metrics_v1.json",
    )
    request = RunCreateRequest(
        job_type=JobType.road,
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content="C04 frozen typhoon road progressive delivery execution",
            disaster_type="typhoon",
            spatial_extent=config["aoi"]["spatial_extent"],
        ),
        target_crs=config["aoi"]["target_crs"],
        input_strategy=RunInputStrategy.task_driven_auto,
        debug=False,
    )
    stage_records = []
    environment = {
        "GEOFUSION_LOCAL_ONLY": "1",
        "GEOFUSION_KG_BACKEND": "memory",
        "GEOFUSION_DISABLE_ARTIFACT_REUSE": "1",
        "GEOFUSION_CELERY_EAGER": "1",
        "GEOFUSION_MAX_PLAN_REVISIONS": "1",
        "GEOFUSION_VALIDATOR_MODE": "enforce",
        "GEOFUSION_LLM_PROVIDER": "mock",
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
                stage_dir = evidence_root / "stages" / stage["stage_id"]
                stage_dir.mkdir(parents=True, exist_ok=True)
                prepared = prepare_stage_sources(
                    manifest=staging_manifest,
                    stage=ExperimentStageDeclaration(
                        stage_id=stage["stage_id"],
                        action="create",
                        active_source_ids=stage["active_source_ids"],
                    ),
                    data_root=data_root,
                    evidence_dir=stage_dir,
                )
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
                    _write_json(
                        evidence_root / "experiment_failure.json",
                        {
                            "protocol_id": protocol["protocol_id"],
                            "case_identity": config["case_identity"],
                            "failed_stage_id": stage["stage_id"],
                            "failed_run_id": status.run_id,
                            "error": current.error,
                            "runtime_runs_created": len(stage_records),
                            "stages_completed": sum(
                                1 for item in stage_records if item["runtime_succeeded"]
                            ),
                            **_fusion_execution_counts(stage_records),
                            "second_stage_started": any(
                                item["stage_id"] == "microsoft_arrival" for item in stage_records
                            ),
                            "automatic_retry_performed": False,
                            "stage_records": stage_records,
                        },
                    )
                    raise RuntimeError(f"P4 C04 stage failed: {stage['stage_id']} run_id={status.run_id}")
        finally:
            service.shutdown()

    evaluation = _evaluate_stages(stage_records)
    _write_json(evidence_root / "selected_resolved_executed_evaluated.json", evaluation)
    _write_json(evidence_root / "supersession.json", evaluation["evaluated"]["supersession"])
    result = {
        "protocol_id": protocol["protocol_id"],
        "case_identity": config["case_identity"],
        "stage_records": stage_records,
        "evaluation": evaluation,
        "passed": evaluation["passed"],
        "claim_boundary": protocol["evaluation_boundary"]["claim_boundary"],
    }
    _write_json(evidence_root / "experiment_result.json", result)
    return result


def _fusion_execution_counts(stage_records: list[dict[str, Any]]) -> dict[str, int]:
    events = [
        event
        for record in stage_records
        for event in (record.get("events") or [])
        if isinstance(event, dict)
    ]
    return {
        "fusion_algorithm_executions_started": sum(
            event.get("kind") in {"execution_started", "large_area_tile_started"}
            for event in events
        ),
        "fusion_algorithm_executions_completed": sum(
            event.get("kind") in {"execution_completed", "large_area_tile_completed"}
            for event in events
        ),
    }


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
    frozen_path = run_dir / "frozen_plan_input.json"
    injected = _read_json(frozen_path)
    artifact = status.get("artifact") or {}
    artifact_path = Path(str(artifact.get("path") or ""))
    injected_events = [event for event in events if event.get("kind") == "frozen_plan_injected"]
    component_coverage = _last_event_detail(events, "task_inputs_resolved", "component_coverage") or {}
    materialization = _materialization_evidence(events)
    quality = _quality_evidence(events)
    return {
        "stage_id": stage["stage_id"],
        "run_id": run_id,
        "runtime_phase": status["phase"],
        "runtime_succeeded": status["phase"] == "succeeded" and artifact_path.is_file(),
        "prepared_inputs": prepared,
        "injected_plan_sha256": _workflow_plan_semantic_hash(WorkflowPlan.model_validate(injected)),
        "expected_plan_sha256": expected_plan_hash,
        "frozen_plan_injected_event_count": len(injected_events),
        "selected_delivery_state": str((injected.get("context") or {}).get("decision") or ""),
        "component_coverage": component_coverage,
        "source_materialization": materialization,
        "quality_evaluation": quality,
        "provisional_evidence": {
            "declared_delayed_source_ids": list(stage.get("delayed_source_ids") or []),
            "observed_non_empty_source_ids": _non_empty_source_ids(component_coverage),
            "observed_unmaterialized_source_ids": _unmaterialized_source_ids(component_coverage),
        },
        "artifact_path": str(artifact_path) if artifact_path.is_file() else None,
        "artifact_sha256": sha256_file(artifact_path) if artifact_path.is_file() else None,
        "events": events,
    }


def _evaluate_stages(records: list[dict[str, Any]]) -> dict[str, Any]:
    if len(records) != 2:
        return {
            "selected": {"source": "frozen_formal_plan", "delivery_state": "degraded"},
            "resolved": {"logical_source_id": "catalog.typhoon.road", "stage_count": len(records)},
            "executed": {"runs": [record.get("run_id") for record in records]},
            "evaluated": {"stage_artifact_sha256": [], "supersession": {"verified": False}},
            "checks": {"two_stage_records": False},
            "passed": False,
        }
    first, second = records
    first_active = set(first["prepared_inputs"]["active_source_ids"])
    second_active = set(second["prepared_inputs"]["active_source_ids"])
    first_quality = first.get("quality_evaluation") or {}
    second_quality = second.get("quality_evaluation") or {}
    first_coverage = first.get("component_coverage") or {}
    second_coverage = second.get("component_coverage") or {}
    distinct_runs = bool(first.get("run_id")) and first.get("run_id") != second.get("run_id")
    changed_artifact = bool(first.get("artifact_sha256")) and (
        first.get("artifact_sha256") != second.get("artifact_sha256")
    )
    first_osm_non_empty = _component_non_empty(first_coverage, "raw.osm.road")
    first_microsoft_unmaterialized = _component_unmaterialized(first_coverage, "raw.microsoft.road")
    second_osm_non_empty = _component_non_empty(second_coverage, "raw.osm.road")
    second_microsoft_non_empty = _component_non_empty(second_coverage, "raw.microsoft.road")
    independent_quality = (
        _quality_evaluation_valid(first_quality)
        and _quality_evaluation_valid(second_quality)
        and _coverage_matches(first_coverage, first_quality.get("component_coverage"))
        and _coverage_matches(second_coverage, second_quality.get("component_coverage"))
        and first_quality.get("report_sha256") != second_quality.get("report_sha256")
    )
    closure_changed = first_microsoft_unmaterialized and second_microsoft_non_empty
    supersession = {
        "verified": (
            distinct_runs
            and changed_artifact
            and first_osm_non_empty
            and second_osm_non_empty
            and closure_changed
            and independent_quality
        ),
        "reason": "raw.microsoft.road_materialized",
        "superseded": {
            "stage_id": first.get("stage_id"),
            "run_id": first.get("run_id"),
            "artifact_sha256": first.get("artifact_sha256"),
            "quality_report_sha256": first_quality.get("report_sha256"),
        },
        "superseding": {
            "stage_id": second.get("stage_id"),
            "run_id": second.get("run_id"),
            "artifact_sha256": second.get("artifact_sha256"),
            "quality_report_sha256": second_quality.get("report_sha256"),
        },
        "component_transition": {
            "source_id": "raw.microsoft.road",
            "before": first_coverage.get("raw.microsoft.road"),
            "after": second_coverage.get("raw.microsoft.road"),
        },
    }
    checks = {
        "two_stage_records": [first.get("stage_id"), second.get("stage_id")]
        == ["osm_provisional", "microsoft_arrival"],
        "two_runs_completed": len(records) == 2 and all(record["runtime_succeeded"] for record in records),
        "independent_runtime_runs": distinct_runs,
        "exact_plan_injected": all(
            record["injected_plan_sha256"] == record["expected_plan_sha256"]
            and record["frozen_plan_injected_event_count"] == 1
            for record in records
        ),
        "provisional_stage_excludes_microsoft": "raw.microsoft.road" not in first_active,
        "arrival_stage_includes_microsoft": "raw.microsoft.road" in second_active,
        "provisional_osm_materialized_non_empty": first_osm_non_empty,
        "provisional_microsoft_not_materialized": first_microsoft_unmaterialized,
        "provisional_gap_grounded": (
            first.get("selected_delivery_state") == "degraded"
            and "raw.microsoft.road"
            in set((first.get("provisional_evidence") or {}).get("declared_delayed_source_ids") or [])
            and first_microsoft_unmaterialized
        ),
        "arrival_osm_and_microsoft_materialized_non_empty": second_osm_non_empty
        and second_microsoft_non_empty,
        "materialization_manifests_recorded": all(
            _materialization_evidence_valid(
                record.get("source_materialization") or {},
                record.get("component_coverage") or {},
            )
            for record in records
        ),
        "quality_evaluated_each_stage": independent_quality,
        "artifacts_hashed": all(record["artifact_sha256"] for record in records),
        "new_artifact_observed": changed_artifact,
        "supersession_evidence_complete": supersession["verified"],
    }
    return {
        "selected": {"source": "frozen_formal_plan", "delivery_state": "degraded"},
        "resolved": {"logical_source_id": "catalog.typhoon.road", "stage_count": 2},
        "executed": {"runs": [record["run_id"] for record in records]},
        "evaluated": {
            "stage_artifact_sha256": [record["artifact_sha256"] for record in records],
            "supersession": supersession,
        },
        "checks": checks,
        "passed": all(checks.values()),
    }


def _last_event_detail(events: list[dict[str, Any]], kind: str, key: str) -> Any:
    for event in reversed(events):
        if event.get("kind") == kind:
            return (event.get("details") or {}).get(key)
    return None


def _materialization_evidence(events: list[dict[str, Any]]) -> dict[str, Any]:
    path_value = _last_event_detail(events, "task_inputs_resolved", "source_materialization_manifest_path")
    path = Path(str(path_value or ""))
    if not path.is_file():
        return {"path": str(path) if path_value else None, "sha256": None, "manifest": None}
    return {"path": str(path), "sha256": sha256_file(path), "manifest": _read_json(path)}


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


def _component_non_empty(coverage: dict[str, Any], source_id: str) -> bool:
    value = coverage.get(source_id)
    if not isinstance(value, dict) or not value.get("path"):
        return False
    try:
        return int(value.get("feature_count") or 0) > 0
    except (TypeError, ValueError):
        return False


def _component_unmaterialized(coverage: dict[str, Any], source_id: str) -> bool:
    value = coverage.get(source_id)
    if not isinstance(value, dict):
        return False
    try:
        return int(value.get("feature_count") or 0) == 0 and not value.get("path")
    except (TypeError, ValueError):
        return False


def _non_empty_source_ids(coverage: dict[str, Any]) -> list[str]:
    return sorted(source_id for source_id in coverage if _component_non_empty(coverage, source_id))


def _unmaterialized_source_ids(coverage: dict[str, Any]) -> list[str]:
    return sorted(source_id for source_id in coverage if _component_unmaterialized(coverage, source_id))


def _materialization_evidence_valid(evidence: dict[str, Any], coverage: dict[str, Any]) -> bool:
    manifest = evidence.get("manifest")
    return (
        bool(evidence.get("sha256"))
        and isinstance(manifest, dict)
        and _coverage_matches(coverage, manifest.get("component_coverage"))
    )


def _coverage_matches(expected: dict[str, Any], observed: Any) -> bool:
    return isinstance(observed, dict) and observed == expected


def _quality_evaluation_valid(evidence: dict[str, Any]) -> bool:
    return (
        int(evidence.get("event_count") or 0) >= 1
        and evidence.get("accepted") is True
        and bool(evidence.get("report_path"))
        and bool(evidence.get("report_sha256"))
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
        plan.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight or execute the frozen P4 C04 road protocol.")
    parser.add_argument("--freeze", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.preflight:
        result = preflight_p4_c04_runner(args.freeze)
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result["passed"] else 2
    result = execute_p4_c04_runner(args.freeze)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
