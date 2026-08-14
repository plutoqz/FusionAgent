from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.validator import WorkflowValidator
from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import WorkflowPlan
from schemas.research_case_manifest import load_research_case_manifest
from schemas.research_llm_pilot import ResearchPlanningDecision
from services.research_plan_runtime_adapter import ResearchPlanRuntimeAdapter


CASE_ID = "C02"
CONDITION = "llm_full_contract_kg"
FORMAL_RUN_ID = "formal-c02-llm_full_contract_kg-r1"
PROTOCOL_ID = "fusionagent.p4.c02-water-road-e2e.v2"
INVENTORY_PROTOCOL_ID = "fusionagent.p4.c02-asset-inventory.s2"
STAGE_TASK_KINDS = ("water_polygon", "waterways", "road")
GAP_TASK_KINDS = ("building", "poi")
EVIDENCE_ROOT = Path(r"D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c02-water-road-e2e-r2")
DEFAULT_FORMAL_ROOT = Path(r"D:\code\fusionagent-evidence\p3-planning-formal\2026-08-13-deepseek-v4-flash-formal-r1")
DEFAULT_INVENTORY = Path(r"D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c02-asset-inventory-s2-r3\asset_inventory.json")
DEFAULT_S1_AUDIT = Path(r"D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c02-selected-resolved-s1-r2\selected_resolved_audit.json")


def build_p4_c02_freeze(
    *,
    formal_root: Path,
    inventory_path: Path,
    s1_audit_path: Path,
    case_manifest_path: Path,
    evidence_root: Path,
    implementation_commit: str,
) -> dict[str, Any]:
    formal_root = formal_root.resolve()
    inventory_path = inventory_path.resolve()
    s1_audit_path = s1_audit_path.resolve()
    case_manifest_path = case_manifest_path.resolve()
    evidence_root = evidence_root.resolve()
    schedule_path = formal_root / "schedule.json"
    result_path = formal_root / "runs" / FORMAL_RUN_ID / "result.json"
    schedule = _read_json(schedule_path)
    result = _read_json(result_path)
    inventory = _read_json(inventory_path)
    s1_audit = _read_json(s1_audit_path)

    scheduled = [item for item in schedule["items"] if item["run_id"] == FORMAL_RUN_ID]
    if len(scheduled) != 1 or scheduled[0]["case_id"] != CASE_ID or scheduled[0]["knowledge_condition"] != CONDITION:
        raise ValueError("C02 formal schedule identity is not exact")
    if result.get("run_id") != FORMAL_RUN_ID or result.get("success") is not True:
        raise ValueError("C02 formal result is missing or unsuccessful")
    if s1_audit.get("passed") is not True or s1_audit.get("claim_eligible") is not False:
        raise ValueError("S1 selected/resolved audit is not a passed diagnostic audit")
    if inventory.get("protocol_id") != INVENTORY_PROTOCOL_ID or inventory.get("passed") is not True:
        raise ValueError("S2 real asset inventory is not passed")
    if any(value != 0 for value in (inventory.get("runtime_calls") or {}).values()):
        raise ValueError("S2 inventory unexpectedly performed runtime calls")

    case_manifest = load_research_case_manifest(case_manifest_path)
    case = next(item for item in case_manifest.cases if item.case_id == CASE_ID)
    selected = ResearchPlanningDecision.model_validate(result["plan"])
    repository = InMemoryKGRepository(experience_policy="pinned_snapshot")
    resolution = ResearchPlanRuntimeAdapter(repository).resolve(
        case=case,
        condition=CONDITION,
        decision=selected,
        complete_from_kg=True,
    )
    if resolution.status != "resolved" or resolution.workflow_plan is None:
        raise ValueError("C02 selected plan no longer resolves through frozen KG completion")
    workflow_plan = resolution.workflow_plan
    validation = WorkflowValidator(repository, enforcement_mode="enforce").validate_and_repair(workflow_plan)
    if validation.validation is None or not validation.validation.valid or validation.validation.rejected:
        raise ValueError("C02 resolved workflow failed WorkflowValidator(enforce)")

    by_kind = {item.task_kind: item for item in resolution.task_resolutions}
    if set(by_kind) != set(STAGE_TASK_KINDS + GAP_TASK_KINDS):
        raise ValueError("C02 selected/resolved task set drifted")
    if any(by_kind[kind].resolution_status != "resolved" for kind in STAGE_TASK_KINDS):
        raise ValueError("C02 executable stage resolution is incomplete")
    if any(by_kind[kind].resolution_status == "resolved" for kind in GAP_TASK_KINDS):
        raise ValueError("C02 gap task became executable")

    stage_plans = {}
    for stage_order, task_kind in enumerate(STAGE_TASK_KINDS, start=1):
        task_resolution = by_kind[task_kind]
        task = next(item for item in workflow_plan.tasks if item.task_id == task_resolution.workflow_task.task_id)
        stage_plan = workflow_plan.model_copy(deep=True)
        stage_plan.tasks = [task.model_copy(update={"step": 1, "depends_on": []})]
        stage_plan.data_needs = [item for item in stage_plan.data_needs if item.task_id == task.task_id]
        stage_plan.repair_strategies = [
            item for item in stage_plan.repair_strategies if task.task_id in item.applies_to_task_ids
        ]
        stage_plan.context = {**stage_plan.context, "c02_stage_order": stage_order, "c02_stage_task_kind": task_kind}
        stage_validation = WorkflowValidator(repository, enforcement_mode="enforce").validate_and_repair(stage_plan)
        if stage_validation.validation is None or not stage_validation.validation.valid or stage_validation.validation.rejected:
            raise ValueError(f"C02 stage plan failed validation: {task_kind}")
        stage_plans[task_kind] = stage_plan.model_dump(mode="json")

    execution_config = {
        "protocol_id": PROTOCOL_ID,
        "case_identity": {
            "case_id": CASE_ID,
            "case_version": case.version,
            "variant_id": "formal-llm-full-contract-kg-c02-caracas-r2",
            "aoi_id": "caracas-capital-district-v1",
            "run_id": "p4-c02-water-road-caracas-r2",
            "formal_run_id": FORMAL_RUN_ID,
        },
        "aoi": {
            "spatial_extent": "bbox(-67.17,10.38,-66.86,10.57)",
            "bbox": [-67.17, 10.38, -66.86, 10.57],
            "target_crs": "EPSG:32619",
            "boundary_source_id": "aoi.venezuela_capital_district",
            "scale_semantics": "bounded_caracas_capital_district_single_case",
        },
        "stage_order": list(STAGE_TASK_KINDS),
        "stages": [
            {
                "stage_id": task_kind,
                "task_kind": task_kind,
                "action": "independent_task_run",
                "active_source_ids": list((by_kind[task_kind].resolved or {}).get("component_source_ids", []))
                + ["aoi.venezuela_capital_district"],
                "required_trace": ["selected", "resolved", "executed", "evaluated", "quality_result", "artifact_hash"],
                "acceptance": {"non_empty_components_required": True, "semantic_contract_valid": True, "artifact_hash_required": True},
            }
            for task_kind in STAGE_TASK_KINDS
        ],
        "gap_declaration": {
            "building": {"status": "gap", "reason_code": "DELIVERY_STATE_GAP", "materialize": False},
            "poi": {"status": "gap", "reason_code": "DELIVERY_STATE_GAP", "materialize": False},
        },
        "runtime": {
            "kg_backend": "memory_pinned_snapshot",
            "local_only": True,
            "llm_calls": 0,
            "provider_calls": 0,
            "fusion_runs": 0,
            "planner_mode": "frozen_stage_plan_injection",
            "fallback": "forbidden",
            "automatic_retries": 0,
            "json_salvage": False,
            "artifact_reuse": False,
            "workers": 1,
        },
        "budget": {
            "case_count": 1,
            "stage_count": len(STAGE_TASK_KINDS),
            "max_wall_seconds_per_stage": 1800,
            "max_total_wall_seconds": 5400,
            "max_evidence_bytes": 10 * 1024**3,
            "max_provider_network_calls": 0,
            "max_llm_calls": 0,
        },
        "evidence_root": str(evidence_root),
        "abort_conditions": [
            "frozen_stage_plan_hash_mismatch",
            "unplanned_source_or_algorithm_substitution",
            "source_semantic_contract_invalid_or_unavailable",
            "missing_required_component_or_trace",
            "stage_timeout_or_budget_exceeded",
            "evidence_root_nonempty_before_execution",
            "fallback_retry_or_artifact_reuse_observed",
        ],
    }
    implementation_files = {
        path: _file_hash(REPO_ROOT / path)
        for path in (
            "services/research_plan_runtime_adapter.py",
            "services/source_field_profile_registry.py",
            "services/source_semantic_contract_service.py",
            "services/track_b_source_normalization.py",
            "services/agent_run_service.py",
            "services/domain_fusion_runners.py",
            "services/run_writeback_service.py",
            "services/run_state_store.py",
            "schemas/task_kind.py",
            "scripts/profile_p4_c02_assets.py",
            "scripts/freeze_p4_c02_protocol.py",
            "scripts/run_p4_c02_e2e.py",
        )
    }
    protocol = {
        "protocol_id": PROTOCOL_ID,
        "status": "protocol_frozen_preflight_ready",
        "protocol_ready": True,
        "execution_ready": True,
        "execution_blockers": [],
        "runner_contract": {
            "entrypoint": "scripts/run_p4_c02_e2e.py",
            "plan_injection": "stage_plan_semantic_hash_locked",
            "stage_execution": "three_independent_task_runs",
            "planner_calls": 0,
            "replanning": "forbidden",
            "execution_validation_gate": "workflow_validator_enforce",
            "source_semantic_validation": "normalized_algorithm_input_fail_closed",
            "gap_policy": "building_and_poi_explicit_gap",
            "generic_grounding_probe": "diagnostic_only",
            "frozen_plan_persistence": "canonical_no_derived_fields",
        },
        "implementation_commit": implementation_commit,
        "implementation_files": implementation_files,
        "knowledge_identity": repository.get_knowledge_identity(),
        "input_evidence": {
            "case_manifest": _input_ref(case_manifest_path),
            "formal_schedule": _input_ref(schedule_path),
            "formal_result": _input_ref(result_path),
            "s1_selected_resolved_audit": _input_ref(s1_audit_path),
            "s2_asset_inventory": _input_ref(inventory_path),
        },
        "frozen_artifact_hashes": {
            "selected_plan": _semantic_hash(selected.model_dump(mode="json")),
            "resolved_plan": _semantic_hash(resolution.model_dump(mode="json")),
            "workflow_plan": _semantic_hash(workflow_plan.model_dump(mode="json")),
            "stage_plans": {kind: _semantic_hash(plan) for kind, plan in stage_plans.items()},
            "execution_config": _semantic_hash(execution_config),
            "asset_inventory": _semantic_hash(inventory),
        },
        "evaluation_boundary": {
            "claim_eligible": False,
            "claim_boundary": "One bounded Caracas C02 run can provide selected/resolved/executed/evaluated trace and artifact evidence only; it cannot establish comparative superiority, statistical significance, or cross-AOI validity.",
            "selected_delivery_state": selected.tasks[0].delivery_state,
            "gap_task_kinds": list(GAP_TASK_KINDS),
        },
        "semantic_contracts": inventory["semantic_contracts"],
    }
    return {
        "protocol": protocol,
        "selected_plan": selected.model_dump(mode="json"),
        "resolved_plan": resolution.model_dump(mode="json"),
        "workflow_plan": workflow_plan.model_dump(mode="json"),
        "stage_plans": stage_plans,
        "execution_config": execution_config,
        "asset_inventory": inventory,
        "case_manifest": _read_json(case_manifest_path),
    }


def write_p4_c02_freeze(output: Path, payload: dict[str, Any]) -> dict[str, Any]:
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Freeze output is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    for key, filename in (
        ("protocol", "protocol.json"),
        ("selected_plan", "selected_plan.json"),
        ("resolved_plan", "resolved_plan.json"),
        ("workflow_plan", "workflow_plan.json"),
        ("stage_plans", "stage_plans.json"),
        ("execution_config", "execution_config.json"),
        ("asset_inventory", "asset_inventory.json"),
        ("case_manifest", "case_manifest_snapshot.json"),
    ):
        _write_json(output / filename, payload[key])
    audit = verify_p4_c02_freeze(output)
    _write_json(output / "freeze_audit.json", audit)
    return audit


def verify_p4_c02_freeze(root: Path) -> dict[str, Any]:
    root = root.resolve()
    protocol = _read_json(root / "protocol.json")
    selected = _read_json(root / "selected_plan.json")
    resolved = _read_json(root / "resolved_plan.json")
    workflow = _read_json(root / "workflow_plan.json")
    stages = _read_json(root / "stage_plans.json")
    config = _read_json(root / "execution_config.json")
    inventory = _read_json(root / "asset_inventory.json")
    expected = protocol["frozen_artifact_hashes"]
    checks = {
        "protocol_id": protocol.get("protocol_id") == PROTOCOL_ID,
        "protocol_ready": protocol.get("protocol_ready") is True and protocol.get("execution_blockers") == [],
        "selected_plan_hash": _semantic_hash(selected) == expected["selected_plan"],
        "resolved_plan_hash": _semantic_hash(resolved) == expected["resolved_plan"],
        "workflow_plan_hash": _semantic_hash(workflow) == expected["workflow_plan"],
        "stage_plan_hashes": all(_semantic_hash(stages[kind]) == expected["stage_plans"][kind] for kind in STAGE_TASK_KINDS),
        "execution_config_hash": _semantic_hash(config) == expected["execution_config"],
        "asset_inventory_hash": _semantic_hash(inventory) == expected["asset_inventory"],
        "input_evidence_hashes": all(
            Path(item["path"]).is_file() and _file_hash(Path(item["path"])) == item["sha256"]
            for item in protocol["input_evidence"].values()
        ),
        "implementation_file_hashes": all(
            _file_hash(REPO_ROOT / path) == digest for path, digest in protocol["implementation_files"].items()
        ),
        "inventory_passed": inventory.get("passed") is True
        and all(item["validation"].get("valid") is True for item in inventory["semantic_contracts"].values()),
        "zero_runtime_calls": inventory.get("runtime_calls") == {"fusion_runs": 0, "llm_calls": 0, "provider_calls": 0},
        "evidence_root_empty": not Path(config["evidence_root"]).exists()
        or not any(Path(config["evidence_root"]).iterdir()),
    }
    try:
        plan = WorkflowPlan.model_validate(workflow)
        repo = InMemoryKGRepository(experience_policy="pinned_snapshot")
        validation = WorkflowValidator(repo, enforcement_mode="enforce").validate_and_repair(plan)
        checks["workflow_validator_enforce"] = bool(validation.validation and validation.validation.valid and not validation.validation.rejected)
        checks["stage_semantics"] = list(stages) is not None and set(stages) == set(STAGE_TASK_KINDS)
    except (ValueError, KeyError, TypeError):
        checks["workflow_validator_enforce"] = False
        checks["stage_semantics"] = False
    return {"report_type": "p4_c02_protocol_freeze_audit", "checks": checks, "passed": all(checks.values())}


def preflight_p4_c02_protocol(freeze_root: Path) -> dict[str, Any]:
    freeze_root = freeze_root.resolve()
    audit = verify_p4_c02_freeze(freeze_root)
    protocol = _read_json(freeze_root / "protocol.json")
    config = _read_json(freeze_root / "execution_config.json")
    stages = _read_json(freeze_root / "stage_plans.json")
    checks = {
        "freeze_audit": audit["passed"] is True,
        "execution_ready": protocol.get("execution_ready") is True and protocol.get("execution_blockers") == [],
        "stage_order": config.get("stage_order") == list(STAGE_TASK_KINDS),
        "stage_plans_present": set(stages) == set(STAGE_TASK_KINDS),
        "zero_llm_calls": config["runtime"]["llm_calls"] == 0 and config["budget"]["max_llm_calls"] == 0,
        "local_only": config["runtime"]["local_only"] is True and config["budget"]["max_provider_network_calls"] == 0,
        "fallback_forbidden": config["runtime"]["fallback"] == "forbidden" and config["runtime"]["automatic_retries"] == 0,
        "artifact_reuse_disabled": config["runtime"]["artifact_reuse"] is False,
        "evidence_root_empty": not Path(config["evidence_root"]).exists() or not any(Path(config["evidence_root"]).iterdir()),
    }
    return {
        "report_type": "p4_c02_runner_preflight",
        "protocol_id": protocol.get("protocol_id"),
        "freeze_root": str(freeze_root),
        "evidence_root": config.get("evidence_root"),
        "checks": checks,
        "passed": all(checks.values()),
        "provider_calls_made": 0,
        "llm_calls_made": 0,
        "fusion_runs_started": 0,
    }


def _input_ref(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "sha256": _file_hash(path), "size_bytes": path.stat().st_size}


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _semantic_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze and preflight C02 selected/resolved E2E protocol without execution.")
    parser.add_argument("--formal-root", type=Path, default=DEFAULT_FORMAL_ROOT)
    parser.add_argument("--inventory", type=Path, default=DEFAULT_INVENTORY)
    parser.add_argument("--s1-audit", type=Path, default=DEFAULT_S1_AUDIT)
    parser.add_argument("--case-manifest", type=Path, default=REPO_ROOT / "docs/current/research-case-manifest-v1.json")
    parser.add_argument("--evidence-root", type=Path, default=EVIDENCE_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--implementation-commit", required=True)
    args = parser.parse_args()
    payload = build_p4_c02_freeze(
        formal_root=args.formal_root,
        inventory_path=args.inventory,
        s1_audit_path=args.s1_audit,
        case_manifest_path=args.case_manifest,
        evidence_root=args.evidence_root,
        implementation_commit=args.implementation_commit,
    )
    audit = write_p4_c02_freeze(args.output, payload)
    preflight = preflight_p4_c02_protocol(args.output)
    _write_json(args.output / "preflight.json", preflight)
    print(json.dumps({"freeze_audit": audit, "preflight": preflight}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if audit["passed"] and preflight["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
