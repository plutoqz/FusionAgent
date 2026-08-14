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

import geopandas as gpd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.validator import WorkflowValidator
from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import RunCreateRequest, RunInputStrategy, RunTrigger, RunTriggerType, WorkflowPlan
from schemas.contract_experiment import ContractExperimentManifest, ExperimentStageDeclaration
from schemas.fusion import JobType
from services.contract_experiment_service import load_experiment_manifest, prepare_stage_sources, sha256_file


PROTOCOL_ID = "fusionagent.p4.c06-failure-screening.v1"
CANDIDATE_ID = "c06-screen-caracas-dual-road-v1"
SOURCE_IDS = ("raw.osm.road", "raw.microsoft.road", "aoi.venezuela_capital_district")
DEFAULT_C04_FREEZE = (
    REPO_ROOT
    / "docs/current/evidence/p4-planning-e2e/2026-08-14-c04-road-protocol-freeze-v5"
)
DEFAULT_FREEZE_ROOT = Path(
    r"D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c06-failure-screening-freeze-v1"
)
DEFAULT_EVIDENCE_ROOT = Path(
    r"D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c06-failure-screening-r1"
)


def build_screening_freeze(
    *,
    c04_freeze_root: Path,
    evidence_root: Path,
    implementation_commit: str,
) -> dict[str, Any]:
    c04_freeze_root = c04_freeze_root.resolve()
    evidence_root = evidence_root.resolve()
    if evidence_root.exists() and any(evidence_root.iterdir()):
        raise FileExistsError(f"Screening evidence root is not empty: {evidence_root}")

    c04_protocol_path = c04_freeze_root / "protocol.json"
    c04_inventory_path = c04_freeze_root / "asset_inventory.json"
    c04_plan_path = c04_freeze_root / "workflow_plan.json"
    c04_protocol = _read_json(c04_protocol_path)
    inventory = _read_json(c04_inventory_path)
    _validate_source_inventory(inventory)
    asset_manifest_ref = c04_protocol["input_evidence"]["asset_manifest"]
    asset_manifest_path = Path(asset_manifest_ref["path"])
    if _file_hash(asset_manifest_path) != asset_manifest_ref["sha256"]:
        raise ValueError("C04 source asset manifest hash drifted")

    plan = WorkflowPlan.model_validate(_read_json(c04_plan_path)).model_copy(deep=True)
    plan.workflow_id = "research-c06-failure-screening-caracas-v1"
    plan.trigger.content = "C06 failure mechanism screening for frozen Caracas dual-source road inputs"
    plan.trigger.disaster_type = "flood"
    plan.context = {
        **plan.context,
        "case_id": "C06-screening-v1",
        "condition": "deterministic_failure_screening",
        "screening_candidate_id": CANDIDATE_ID,
    }
    plan.tasks[0].input.data_source_id = "catalog.flood.road"
    plan.validation = None
    repository = InMemoryKGRepository(experience_policy="pinned_snapshot")
    plan = WorkflowValidator(repository, enforcement_mode="enforce").validate_and_repair(plan)
    if plan.validation is None or not plan.validation.valid or plan.validation.rejected:
        raise ValueError("C06 screening workflow did not pass WorkflowValidator(enforce)")

    candidate_set = {
        "candidate_set_id": "fusionagent.c06.failure-screening.candidates.v1",
        "frozen_before_screening": True,
        "candidate_count": 1,
        "selection_boundary": (
            "Only the repository-declared Caracas snapshot has both OSM and Microsoft road sources. "
            "No candidate may be added after screening starts."
        ),
        "candidates": [
            {
                "candidate_id": CANDIDATE_ID,
                "aoi_id": "caracas-capital-district-v1",
                "spatial_extent": "bbox(-67.17,10.38,-66.86,10.57)",
                "target_crs": "EPSG:32619",
                "source_ids": list(SOURCE_IDS[:2]),
                "aoi_source_id": SOURCE_IDS[2],
                "algorithm_id": "algo.fusion.road.conflation.v7",
                "quality_policy_id": "quality.default.road.v1",
                "product_contract_id": "contract.road.fused.v1",
                "asset_inventory": inventory,
            }
        ],
    }
    execution_config = {
        "protocol_id": PROTOCOL_ID,
        "screening_run_id": "p4-c06-failure-screening-caracas-r1",
        "candidate_order": [CANDIDATE_ID],
        "evidence_root": str(evidence_root),
        "aoi": {
            "spatial_extent": "bbox(-67.17,10.38,-66.86,10.57)",
            "target_crs": "EPSG:32619",
        },
        "active_source_ids": list(SOURCE_IDS),
        "runtime": {
            "local_only": True,
            "planner_mode": "frozen_screening_plan_injection",
            "llm_calls": 0,
            "provider_calls": 0,
            "automatic_retries": 0,
            "recovery": "forbidden_during_screening",
            "fallback": "forbidden",
            "artifact_reuse": False,
            "workers": 1,
        },
        "budget": {
            "candidate_count": 1,
            "max_wall_seconds": 3600,
            "max_llm_calls": 0,
            "max_provider_network_calls": 0,
        },
        "failure_taxonomy": {
            "eligible": "quality_gate_rejected_fusion_output",
            "ineligible": [
                "source_semantic_contract_invalid",
                "source_unavailable",
                "algorithm_runtime_error",
                "system_failure",
                "manually_modified_input",
            ],
        },
    }
    implementation_files = {
        path: _file_hash(REPO_ROOT / path)
        for path in (
            "fusion_algorithms/road_conflation_v7.py",
            "services/agent_run_service.py",
            "services/domain_fusion_runners.py",
            "services/run_writeback_service.py",
            "services/quality_gate_service.py",
            "services/artifact_evaluation_service.py",
            "services/artifact_repair_service.py",
            "services/source_semantic_contract_service.py",
            "services/track_b_source_normalization.py",
            "scripts/run_p4_c06_failure_screening.py",
        )
    }
    protocol = {
        "protocol_id": PROTOCOL_ID,
        "status": "screening_protocol_frozen_preflight_ready",
        "screening_ready": True,
        "execution_blockers": [],
        "implementation_commit": implementation_commit,
        "implementation_files": implementation_files,
        "knowledge_identity": repository.get_knowledge_identity(),
        "input_evidence": {
            "c04_protocol": _input_ref(c04_protocol_path),
            "c04_asset_inventory": _input_ref(c04_inventory_path),
            "c04_workflow_plan": _input_ref(c04_plan_path),
            "asset_manifest": _input_ref(asset_manifest_path),
        },
        "frozen_hashes": {
            "candidate_set": _semantic_hash(candidate_set),
            "workflow_plan": _workflow_plan_hash(plan),
            "execution_config": _semantic_hash(execution_config),
        },
        "research_boundary": {
            "formal_capability_experiment": False,
            "failure_mechanism_screening": True,
            "claim_eligible": False,
            "no_posthoc_candidate_addition": True,
            "no_input_mutation": True,
            "no_threshold_change": True,
            "no_recovery_or_retry": True,
        },
    }
    return {
        "protocol": protocol,
        "candidate_set": candidate_set,
        "workflow_plan": plan.model_dump(mode="json"),
        "execution_config": execution_config,
    }


def write_screening_freeze(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    root = root.resolve()
    if root.exists() and any(root.iterdir()):
        raise FileExistsError(f"Screening freeze root is not empty: {root}")
    root.mkdir(parents=True, exist_ok=True)
    for key, filename in (
        ("protocol", "protocol.json"),
        ("candidate_set", "candidate_set.json"),
        ("workflow_plan", "workflow_plan.json"),
        ("execution_config", "execution_config.json"),
    ):
        _write_json(root / filename, payload[key])
    audit = verify_screening_freeze(root)
    _write_json(root / "freeze_audit.json", audit)
    preflight = preflight_screening(root)
    _write_json(root / "preflight.json", preflight)
    return {"freeze_audit": audit, "preflight": preflight}


def verify_screening_freeze(root: Path) -> dict[str, Any]:
    root = root.resolve()
    protocol = _read_json(root / "protocol.json")
    candidate_set = _read_json(root / "candidate_set.json")
    plan = WorkflowPlan.model_validate(_read_json(root / "workflow_plan.json"))
    config = _read_json(root / "execution_config.json")
    expected = protocol["frozen_hashes"]
    checks = {
        "protocol_id": protocol.get("protocol_id") == PROTOCOL_ID,
        "screening_ready": protocol.get("screening_ready") is True
        and protocol.get("execution_blockers") == [],
        "candidate_set_hash": _semantic_hash(candidate_set) == expected["candidate_set"],
        "workflow_plan_hash": _workflow_plan_hash(plan) == expected["workflow_plan"],
        "execution_config_hash": _semantic_hash(config) == expected["execution_config"],
        "single_candidate_frozen": candidate_set.get("frozen_before_screening") is True
        and candidate_set.get("candidate_count") == 1
        and [item["candidate_id"] for item in candidate_set["candidates"]] == [CANDIDATE_ID],
        "input_hashes": all(
            Path(item["path"]).is_file() and _file_hash(Path(item["path"])) == item["sha256"]
            for item in protocol["input_evidence"].values()
        ),
        "implementation_hashes": all(
            _file_hash(REPO_ROOT / path) == digest
            for path, digest in protocol["implementation_files"].items()
        ),
        "asset_hashes": _inventory_hashes_valid(candidate_set["candidates"][0]["asset_inventory"]),
        "evidence_root_empty": not Path(config["evidence_root"]).exists()
        or not any(Path(config["evidence_root"]).iterdir()),
    }
    return {
        "report_type": "p4_c06_failure_screening_freeze_audit",
        "checks": checks,
        "passed": all(checks.values()),
    }


def preflight_screening(root: Path) -> dict[str, Any]:
    root = root.resolve()
    audit = verify_screening_freeze(root)
    protocol = _read_json(root / "protocol.json")
    config = _read_json(root / "execution_config.json")
    checks = {
        "freeze_audit": audit["passed"] is True,
        "screening_ready": protocol.get("screening_ready") is True,
        "single_candidate": config.get("candidate_order") == [CANDIDATE_ID],
        "frozen_sources": config.get("active_source_ids") == list(SOURCE_IDS),
        "local_only": config["runtime"]["local_only"] is True,
        "zero_llm_provider": config["runtime"]["llm_calls"] == 0
        and config["runtime"]["provider_calls"] == 0,
        "no_retry_recovery": config["runtime"]["automatic_retries"] == 0
        and config["runtime"]["recovery"] == "forbidden_during_screening",
        "fallback_reuse_forbidden": config["runtime"]["fallback"] == "forbidden"
        and config["runtime"]["artifact_reuse"] is False,
        "evidence_root_empty": not Path(config["evidence_root"]).exists()
        or not any(Path(config["evidence_root"]).iterdir()),
    }
    return {
        "report_type": "p4_c06_failure_screening_preflight",
        "protocol_id": protocol.get("protocol_id"),
        "freeze_root": str(root),
        "evidence_root": config["evidence_root"],
        "checks": checks,
        "passed": all(checks.values()),
        "fusion_runs_started": 0,
        "llm_calls_made": 0,
        "provider_calls_made": 0,
    }


def execute_screening(root: Path) -> dict[str, Any]:
    root = root.resolve()
    preflight = preflight_screening(root)
    if not preflight["passed"]:
        raise RuntimeError(f"C06 screening preflight failed: {preflight['checks']}")
    protocol = _read_json(root / "protocol.json")
    config = _read_json(root / "execution_config.json")
    plan = WorkflowPlan.model_validate(_read_json(root / "workflow_plan.json"))
    expected_plan_hash = protocol["frozen_hashes"]["workflow_plan"]
    evidence_root = Path(config["evidence_root"])
    if evidence_root.exists():
        raise FileExistsError(f"Screening evidence root already exists: {evidence_root}")
    evidence_root.mkdir(parents=True)
    shutil.copytree(root, evidence_root / "protocol_freeze")
    _write_json(evidence_root / "preflight.json", preflight)

    runtime_root = evidence_root / "runtime"
    data_root = runtime_root / "data_repository"
    download_root = runtime_root / "downloads"
    runs_root = runtime_root / "runs"
    for path in (data_root, download_root, runs_root):
        path.mkdir(parents=True, exist_ok=True)

    asset_manifest_path = Path(protocol["input_evidence"]["asset_manifest"]["path"])
    manifest = load_experiment_manifest(asset_manifest_path)
    selected_sources = [source for source in manifest.sources if source.source_id in SOURCE_IDS]
    if {source.source_id for source in selected_sources} != set(SOURCE_IDS):
        raise RuntimeError("Screening asset manifest is missing a frozen source")
    staging_manifest = ContractExperimentManifest(
        schema_version="1.0.0",
        experiment_id=config["screening_run_id"],
        title="C06 natural quality failure screening inputs",
        data_boundary={"real_external_data": True, "asset_reuse_only": True},
        runtime={"local_only": True},
        sources=selected_sources,
        cases=[],
        metric_definition_path="docs/thesis/contract_case_metrics_v1.json",
    )
    stage_dir = evidence_root / "candidates" / CANDIDATE_ID
    stage_dir.mkdir(parents=True)
    prepared = prepare_stage_sources(
        manifest=staging_manifest,
        stage=ExperimentStageDeclaration(
            stage_id=CANDIDATE_ID,
            action="create",
            active_source_ids=list(SOURCE_IDS),
        ),
        data_root=data_root,
        evidence_dir=stage_dir,
    )
    request = RunCreateRequest(
        job_type=JobType.road,
        trigger=RunTrigger(
            type=RunTriggerType.user_query,
            content="C06 frozen natural quality failure screening",
            disaster_type="flood",
            spatial_extent=config["aoi"]["spatial_extent"],
        ),
        target_crs=config["aoi"]["target_crs"],
        input_strategy=RunInputStrategy.task_driven_auto,
        debug=False,
    )
    environment = {
        "GEOFUSION_LOCAL_ONLY": "1",
        "GEOFUSION_KG_BACKEND": "memory",
        "GEOFUSION_DISABLE_ARTIFACT_REUSE": "1",
        "GEOFUSION_CELERY_EAGER": "1",
        "GEOFUSION_MAX_PLAN_REVISIONS": "1",
        "GEOFUSION_VALIDATOR_MODE": "enforce",
        "GEOFUSION_INPUT_ACQUISITION_TIMEOUT_SECONDS": str(config["budget"]["max_wall_seconds"]),
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
        finally:
            service.shutdown()

    record = _build_screening_record(
        status=current.model_dump(mode="json"),
        events=events,
        prepared=prepared,
        runs_root=runs_root,
        expected_plan_hash=expected_plan_hash,
    )
    _write_json(stage_dir / "screening_record.json", record)
    outcome = _classify_screening_outcome(record)
    checks = {
        "one_run_only": len([path for path in runs_root.iterdir() if path.is_dir()]) == 1,
        "exact_plan_injected": record["injected_plan_sha256"] == expected_plan_hash
        and record["frozen_plan_injected_event_count"] == 1,
        "frozen_sources_prepared": prepared["active_source_ids"] == list(SOURCE_IDS),
        "source_materialization_exact": record["source_materialization"]["sha256"] is not None
        and record["source_materialization"]["component_coverage"] == record["component_coverage"]
        and set(record["component_coverage"]) == set(SOURCE_IDS[:2]),
        "source_semantic_contract_valid": record["source_semantic_contract"]["valid"] is True,
        "quality_report_recorded": record["quality_evaluation"]["report_sha256"] is not None,
        "raw_and_adapted_quality_recorded": record["quality_evaluation"]["raw_quality_passed"] is not None
        and record["quality_evaluation"]["adapted_quality_passed"] is not None,
        "artifact_geometry_hashed": bool(record["vector_artifacts"]),
        "zero_retry_recovery": all(int(event.get("attempt_no") or 0) == 0 for event in events)
        and not any(event.get("kind") in {"replan_started", "artifact_reused"} for event in events),
        "zero_llm_calls": int((record["planning_telemetry"] or {}).get("llm_calls") or 0) == 0,
        "outcome_classified": outcome
        in {"quality_gate_rejected_fusion_output", "no_quality_failure_observed"},
    }
    result = {
        "protocol_id": protocol["protocol_id"],
        "candidate_set_id": "fusionagent.c06.failure-screening.candidates.v1",
        "candidate_id": CANDIDATE_ID,
        "screening_outcome": outcome,
        "natural_quality_failure_observed": outcome == "quality_gate_rejected_fusion_output",
        "eligible_for_s5": outcome == "quality_gate_rejected_fusion_output" and all(checks.values()),
        "candidate_record": record,
        "checks": checks,
        "evidence_integrity_passed": all(checks.values()),
        "claim_eligible": False,
    }
    _write_json(evidence_root / "screening_result.json", result)
    return result


def _build_screening_record(
    *,
    status: dict[str, Any],
    events: list[dict[str, Any]],
    prepared: dict[str, Any],
    runs_root: Path,
    expected_plan_hash: str,
) -> dict[str, Any]:
    run_id = status["run_id"]
    run_dir = runs_root / run_id
    injected = WorkflowPlan.model_validate(_read_json(run_dir / "frozen_plan_input.json"))
    component_coverage = _last_event_detail(events, "task_inputs_resolved", "component_coverage") or {}
    materialization_path = Path(
        str(_last_event_detail(events, "task_inputs_resolved", "source_materialization_manifest_path") or "")
    )
    materialization = _read_json(materialization_path) if materialization_path.is_file() else None
    semantic_path = Path(str(status.get("source_semantic_contract_path") or ""))
    semantic = _read_json(semantic_path) if semantic_path.is_file() else None
    quality_path = run_dir / "output" / "quality_report.json"
    quality = _read_json(quality_path) if quality_path.is_file() else None
    return {
        "candidate_id": CANDIDATE_ID,
        "run_id": run_id,
        "runtime_phase": status["phase"],
        "runtime_error": status.get("error"),
        "planning_telemetry": status.get("planning_telemetry") or {},
        "prepared_inputs": prepared,
        "component_coverage": component_coverage,
        "source_materialization": {
            "path": str(materialization_path) if materialization_path.is_file() else None,
            "sha256": _plain_file_hash(materialization_path) if materialization_path.is_file() else None,
            "component_coverage": (materialization or {}).get("component_coverage"),
        },
        "injected_plan_sha256": _workflow_plan_hash(injected),
        "expected_plan_sha256": expected_plan_hash,
        "frozen_plan_injected_event_count": sum(event.get("kind") == "frozen_plan_injected" for event in events),
        "source_semantic_contract": {
            "path": str(semantic_path) if semantic_path.is_file() else None,
            "sha256": _plain_file_hash(semantic_path) if semantic_path.is_file() else None,
            "valid": (semantic or {}).get("validation", {}).get("valid"),
            "issues": (semantic or {}).get("validation", {}).get("issues", []),
        },
        "quality_evaluation": {
            "path": str(quality_path) if quality_path.is_file() else None,
            "report_sha256": _plain_file_hash(quality_path) if quality_path.is_file() else None,
            "accepted": (quality or {}).get("accepted"),
            "policy_id": (quality or {}).get("policy_id"),
            "failure_reasons": (quality or {}).get("failure_reasons", []),
            "soft_failure_reasons": (quality or {}).get("soft_failure_reasons", []),
            "raw_quality_passed": (quality or {}).get("raw_quality_passed"),
            "adapted_quality_passed": (quality or {}).get("adapted_quality_passed"),
            "metrics": (quality or {}).get("metrics", {}),
        },
        "vector_artifacts": _profile_vector_artifacts(run_dir / "output"),
        "events": events,
    }


def _classify_screening_outcome(record: dict[str, Any]) -> str:
    semantic = record.get("source_semantic_contract") or {}
    quality = record.get("quality_evaluation") or {}
    if semantic.get("valid") is not True or not quality.get("report_sha256"):
        return "ineligible_non_quality_failure"
    if quality.get("accepted") is False and quality.get("adapted_quality_passed") is False:
        return "quality_gate_rejected_fusion_output"
    if quality.get("accepted") is True:
        return "no_quality_failure_observed"
    return "ineligible_non_quality_failure"


def _profile_vector_artifacts(output_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(output_dir.glob("*.gpkg")):
        frame = gpd.read_file(path)
        rows.append(
            {
                "path": str(path),
                "sha256": _plain_file_hash(path),
                "size_bytes": path.stat().st_size,
                "feature_count": len(frame),
                "crs": str(frame.crs),
                "geometry_types": sorted(str(value) for value in frame.geom_type.dropna().unique()),
                "geometry_sha256": _geometry_hash(frame),
                "null_geometry_count": int(frame.geometry.isna().sum()),
                "invalid_geometry_count": int((~frame.geometry.is_valid & frame.geometry.notna()).sum()),
            }
        )
    return rows


def _geometry_hash(frame: gpd.GeoDataFrame) -> str:
    digest = hashlib.sha256()
    for value in sorted(geom.wkb_hex for geom in frame.geometry if geom is not None):
        digest.update(value.encode("ascii"))
        digest.update(b"\n")
    return "sha256:" + digest.hexdigest()


def _validate_source_inventory(inventory: dict[str, Any]) -> None:
    by_id = {item["source_id"]: item for item in inventory.get("sources", [])}
    if set(SOURCE_IDS) - set(by_id):
        raise ValueError("C04 inventory is missing a C06 screening source")
    if any(int(by_id[source_id]["feature_count"]) <= 0 for source_id in SOURCE_IDS):
        raise ValueError("C06 screening source inventory contains an empty source")
    if not _inventory_hashes_valid(inventory):
        raise ValueError("C06 screening source asset hash drifted")


def _inventory_hashes_valid(inventory: dict[str, Any]) -> bool:
    return all(
        Path(item["path"]).is_file() and sha256_file(Path(item["path"])) == item["sha256"]
        for source in inventory.get("sources", [])
        for item in source.get("files", [])
    )


def _last_event_detail(events: list[dict[str, Any]], kind: str, key: str) -> Any:
    for event in reversed(events):
        if event.get("kind") == kind:
            return (event.get("details") or {}).get(key)
    return None


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


def _input_ref(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "sha256": _file_hash(path), "size_bytes": path.stat().st_size}


def _plain_file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_hash(path: Path) -> str:
    return "sha256:" + _plain_file_hash(path)


def _semantic_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _workflow_plan_hash(plan: WorkflowPlan) -> str:
    payload = json.dumps(
        plan.model_dump(mode="json"), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze, preflight, or execute C06 natural failure screening.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--create-freeze", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--freeze", type=Path, default=DEFAULT_FREEZE_ROOT)
    parser.add_argument("--c04-freeze", type=Path, default=DEFAULT_C04_FREEZE)
    parser.add_argument("--evidence-root", type=Path, default=DEFAULT_EVIDENCE_ROOT)
    parser.add_argument("--implementation-commit")
    args = parser.parse_args()
    if args.create_freeze:
        if not args.implementation_commit:
            parser.error("--implementation-commit is required with --create-freeze")
        payload = build_screening_freeze(
            c04_freeze_root=args.c04_freeze,
            evidence_root=args.evidence_root,
            implementation_commit=args.implementation_commit,
        )
        result = write_screening_freeze(args.freeze, payload)
    elif args.preflight:
        result = preflight_screening(args.freeze)
    else:
        result = execute_screening(args.freeze)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if args.execute:
        return 0 if result["evidence_integrity_passed"] else 2
    return 0 if result.get("passed", result.get("preflight", {}).get("passed", False)) else 2


if __name__ == "__main__":
    raise SystemExit(main())
