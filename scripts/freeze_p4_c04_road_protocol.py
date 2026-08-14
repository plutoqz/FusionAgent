from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import geopandas as gpd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.validator import WorkflowValidator
from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import WorkflowPlan
from schemas.research_case_manifest import load_research_case_manifest
from schemas.research_llm_pilot import ResearchPlanningDecision
from services.contract_experiment_service import hash_input_declaration, load_experiment_manifest, sha256_file
from services.research_plan_runtime_adapter import ResearchPlanRuntimeAdapter


CASE_ID = "C04"
CONDITION = "llm_full_contract_kg"
RUN_ID = "formal-c04-llm_full_contract_kg-r1"
SOURCE_IDS = ("raw.osm.road", "raw.microsoft.road", "aoi.venezuela_capital_district")
V1_PROTOCOL_ID = "fusionagent.p4.c04-road-e2e.v1"
V2_PROTOCOL_ID = "fusionagent.p4.c04-road-e2e.v2"
V3_PROTOCOL_ID = "fusionagent.p4.c04-road-e2e.v3"
V4_PROTOCOL_ID = "fusionagent.p4.c04-road-e2e.v4"
PROTOCOL_ID = "fusionagent.p4.c04-road-e2e.v5"
SUPPORTED_PROTOCOL_IDS = {V1_PROTOCOL_ID, V2_PROTOCOL_ID, V3_PROTOCOL_ID, V4_PROTOCOL_ID, PROTOCOL_ID}


def build_p4_c04_freeze(
    *,
    formal_root: Path,
    readiness_path: Path,
    asset_manifest_path: Path,
    case_manifest_path: Path,
    evidence_root: Path,
    prior_failure_path: Path,
    normalization_replay_path: Path,
    implementation_commit: str,
) -> dict[str, Any]:
    formal_root = formal_root.resolve()
    readiness_path = readiness_path.resolve()
    asset_manifest_path = asset_manifest_path.resolve()
    case_manifest_path = case_manifest_path.resolve()
    evidence_root = evidence_root.resolve()
    prior_failure_path = prior_failure_path.resolve()
    normalization_replay_path = normalization_replay_path.resolve()
    prior_failure = _read_json(prior_failure_path)
    normalization_replay = _read_json(normalization_replay_path)
    _validate_v4_failure(prior_failure)
    _validate_normalization_replay(normalization_replay, prior_failure=prior_failure)

    schedule_path = formal_root / "schedule.json"
    result_path = formal_root / "runs" / RUN_ID / "result.json"
    schedule = _read_json(schedule_path)
    scheduled = [item for item in schedule["items"] if item["run_id"] == RUN_ID]
    if len(scheduled) != 1:
        raise ValueError(f"Expected exactly one frozen schedule item for {RUN_ID}")
    if scheduled[0]["case_id"] != CASE_ID or scheduled[0]["knowledge_condition"] != CONDITION:
        raise ValueError("Frozen schedule identity does not match the P4 C04 selection")

    result = _read_json(result_path)
    if result.get("run_id") != RUN_ID or result.get("success") is not True:
        raise ValueError("Selected formal result is missing or unsuccessful")
    selected_plan = ResearchPlanningDecision.model_validate(result["plan"])
    _validate_selected_plan(selected_plan)

    case_manifest = load_research_case_manifest(case_manifest_path)
    case = next(item for item in case_manifest.cases if item.case_id == CASE_ID)
    readiness = _read_json(readiness_path)
    ready_rows = [
        row
        for row in readiness["runs"]
        if row["case_id"] == CASE_ID and row["condition"] == CONDITION
    ]
    if len(ready_rows) != 1 or ready_rows[0].get("ready") is not True:
        raise ValueError("Selected formal result is not wiring-ready in the frozen readiness audit")
    repository = InMemoryKGRepository(experience_policy="pinned_snapshot")
    resolution = ResearchPlanRuntimeAdapter(repository).resolve(
        case=case,
        condition=CONDITION,
        decision=selected_plan,
    )
    if resolution.status != "resolved" or resolution.workflow_plan is None:
        raise ValueError("Selected formal result no longer resolves through the current runtime adapter")
    workflow_plan = resolution.workflow_plan
    _validate_workflow_repair_closure(workflow_plan)
    validated_plan = WorkflowValidator(repository, enforcement_mode="enforce").validate_and_repair(workflow_plan)
    if validated_plan.validation is None or not validated_plan.validation.valid or validated_plan.validation.rejected:
        raise ValueError("Selected workflow plan did not pass WorkflowValidator(enforce)")

    asset_manifest = load_experiment_manifest(asset_manifest_path)
    source_by_id = {source.source_id: source for source in asset_manifest.sources}
    if any(source_id not in source_by_id for source_id in SOURCE_IDS):
        raise ValueError("Asset manifest is missing a required Caracas road or AOI source")
    asset_inventory = _build_asset_inventory([source_by_id[source_id] for source_id in SOURCE_IDS])
    _validate_asset_overlap(asset_inventory)

    if evidence_root.exists() and any(evidence_root.iterdir()):
        raise ValueError(f"Evidence root must be absent or empty before execution: {evidence_root}")

    execution_config = {
        "protocol_id": PROTOCOL_ID,
        "case_identity": {
            "case_id": CASE_ID,
            "case_version": case.version,
            "variant_id": "formal-llm-full-contract-kg",
            "aoi_id": "caracas-capital-district-v1",
            "run_id": "p4-c04-road-caracas-r4",
            "formal_run_id": RUN_ID,
        },
        "aoi": {
            "spatial_extent": "bbox(-67.17,10.38,-66.86,10.57)",
            "bbox": [-67.17, 10.38, -66.86, 10.57],
            "target_crs": "EPSG:32619",
            "boundary_source_id": "aoi.venezuela_capital_district",
            "scale_semantics": "bounded_large_urban_aoi_for_single_case_execution",
        },
        "source_semantics": {
            "logical_source_id": "catalog.typhoon.road",
            "primary_component_source_id": "raw.osm.road",
            "reference_component_source_id": "raw.microsoft.road",
            "reference_role_required": False,
            "normalization_profile": "normalization.road.microsoft_shapefile.v1",
            "source_feature_id_resolution": "provider_artifact_fid",
            "road_class_resolution": "declared_default:road",
            "strict_validation_layer": "normalized_algorithm_input",
            "missing_reference_representation": "empty_reference_bundle_with_explicit_component_coverage",
            "no_source_substitution": True,
        },
        "stages": [
            {
                "stage_id": "osm_provisional",
                "action": "create",
                "active_source_ids": ["raw.osm.road", "aoi.venezuela_capital_district"],
                "delayed_source_ids": ["raw.microsoft.road"],
                "required_trace": [
                    "selected",
                    "resolved",
                    "executed",
                    "evaluated",
                    "component_coverage",
                    "gap_declaration",
                ],
                "acceptance": {
                    "raw_osm_non_empty": True,
                    "microsoft_not_materialized": True,
                    "provisional_mark_required": True,
                    "artifact_hash_required": True,
                },
            },
            {
                "stage_id": "microsoft_arrival",
                "action": "rerun_with_supersession",
                "active_source_ids": list(SOURCE_IDS),
                "delayed_source_ids": [],
                "retry_failed": False,
                "required_trace": [
                    "selected",
                    "resolved",
                    "executed",
                    "evaluated",
                    "component_coverage",
                    "quality_result",
                    "supersession",
                ],
                "acceptance": {
                    "raw_osm_non_empty": True,
                    "microsoft_non_empty": True,
                    "new_artifact_hash_required": True,
                    "quality_re_evaluation_required": True,
                    "supersedes_stage": "osm_provisional",
                },
            },
        ],
        "runtime": {
            "kg_backend": "memory_pinned_snapshot",
            "local_only": True,
            "llm_calls": 0,
            "planner_mode": "frozen_workflow_plan_injection",
            "fallback": "forbidden",
            "automatic_retries": 0,
            "workers": 1,
            "artifact_reuse": False,
        },
        "budget": {
            "case_count": 1,
            "stage_count": 2,
            "max_wall_seconds_per_stage": 1800,
            "max_total_wall_seconds": 3600,
            "max_evidence_bytes": 10 * 1024**3,
            "max_provider_network_calls": 0,
            "max_llm_calls": 0,
        },
        "evidence_root": str(evidence_root),
        "abort_conditions": [
            "frozen_workflow_plan_not_injected_exactly",
            "unplanned_source_or_algorithm_substitution",
            "microsoft_materialized_during_osm_provisional",
            "missing_required_component_or_trace",
            "stage_timeout_or_budget_exceeded",
            "evidence_root_nonempty_before_execution",
            "normalized_source_semantic_contract_invalid_or_unavailable",
        ],
    }
    _validate_stage_semantics(execution_config)

    implementation_files = {
        path: _file_hash(REPO_ROOT / path)
        for path in (
            "services/research_plan_runtime_adapter.py",
            "fusion_algorithms/road_conflation_v7.py",
            "services/domain_fusion_runners.py",
            "services/run_writeback_service.py",
            "services/artifact_repair_service.py",
            "scripts/audit_p4_planning_e2e_readiness.py",
            "scripts/freeze_p4_c04_road_protocol.py",
            "scripts/run_p4_c04_road_e2e.py",
            "services/agent_run_service.py",
            "services/run_state_store.py",
            "services/source_field_profile_registry.py",
            "services/source_profile_service.py",
            "services/source_semantic_contract_service.py",
            "services/track_b_source_normalization.py",
            "services/track_b_national_scale_service.py",
            "scripts/replay_p4_c04_r3_normalization.py",
        )
    }
    protocol = {
        "protocol_id": PROTOCOL_ID,
        "status": "protocol_frozen_execution_ready",
        "protocol_ready": True,
        "execution_ready": True,
        "execution_blockers": [],
        "runner_contract": {
            "entrypoint": "scripts/run_p4_c04_road_e2e.py",
            "plan_injection": "semantic_hash_locked",
            "stage_execution": "independent_runs_with_explicit_supersession",
            "planner_calls": 0,
            "replanning": "forbidden",
            "execution_validation_gate": "workflow_validator_enforce",
            "generic_grounding_probe": "diagnostic_only",
            "frozen_plan_persistence": "canonical_no_derived_fields",
            "single_source_road_output": "v7_canonical_contract",
            "repair_availability": "product_contract_authorization_intersect_frozen_kg_strategy_nodes",
            "source_semantic_validation": "normalized_algorithm_input_fail_closed",
            "microsoft_identifier_resolution": "provider_artifact_fid",
            "microsoft_road_class_resolution": "declared_default_road",
        },
        "implementation_commit": implementation_commit,
        "implementation_files": implementation_files,
        "knowledge_identity": repository.get_knowledge_identity(),
        "input_evidence": {
            "case_manifest": _input_ref(case_manifest_path),
            "formal_schedule": _input_ref(schedule_path),
            "formal_result": _input_ref(result_path),
            "readiness_v2": _input_ref(readiness_path),
            "asset_manifest": _input_ref(asset_manifest_path),
            "prior_failed_attempt": _input_ref(prior_failure_path),
            "normalization_replay": _input_ref(normalization_replay_path),
        },
        "previous_attempt": {
            "protocol_id": prior_failure["protocol_id"],
            "run_id": prior_failure["failed_run_id"],
            "failed_stage_id": prior_failure["failed_stage_id"],
            "failure_class": "quality_gate_rejected_dangle_metric",
            "automatic_retry_performed": prior_failure["automatic_retry_performed"],
        },
        "frozen_artifact_hashes": {
            "selected_plan": _semantic_hash(selected_plan.model_dump(mode="json")),
            "workflow_plan": _semantic_hash(workflow_plan.model_dump(mode="json")),
            "execution_config": _semantic_hash(execution_config),
            "asset_inventory": _semantic_hash(asset_inventory),
            "source_normalization_contract": _semantic_hash(normalization_replay["normalized_contract"]),
        },
        "evaluation_boundary": {
            "selected_delivery_state": selected_plan.tasks[0].delivery_state,
            "gold_allowed_delivery_states": case.gold_rubric.allowed_delivery_states["road"],
            "planning_rubric_mismatch_preserved": selected_plan.tasks[0].delivery_state
            not in case.gold_rubric.allowed_delivery_states["road"],
            "claim_eligible": False,
            "claim_boundary": (
                "A single bounded C04 run can provide execution trace and artifact evidence only. "
                "It cannot establish comparative superiority, statistical significance, or cross-AOI validity."
            ),
        },
        "asset_reuse_boundary": (
            "Only the Caracas source files and AOI boundary are reused from the older Freeze C manifest. "
            "The older C04 water case, runtime outputs, metrics, and claims are not reused."
        ),
        "normalization_evidence": {
            "report": _input_ref(normalization_replay_path),
            "contract_valid": normalization_replay["normalized_contract"]["validation"]["valid"],
            "microsoft_normalization_profile": normalization_replay["normalized_contract"]["sources"]
            ["raw.microsoft.road"]["normalization_profile"],
            "quality_replay_accepted": normalization_replay["quality_replay"]["accepted"],
            "claim_boundary": normalization_replay["claim_boundary"],
        },
    }
    return {
        "protocol": protocol,
        "selected_plan": selected_plan.model_dump(mode="json"),
        "workflow_plan": workflow_plan.model_dump(mode="json"),
        "execution_config": execution_config,
        "asset_inventory": asset_inventory,
    }


def write_p4_c04_freeze(output: Path, payload: dict[str, Any]) -> dict[str, Any]:
    output = output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Freeze output is not empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    for key, filename in (
        ("protocol", "protocol.json"),
        ("selected_plan", "selected_plan.json"),
        ("workflow_plan", "workflow_plan.json"),
        ("execution_config", "execution_config.json"),
        ("asset_inventory", "asset_inventory.json"),
    ):
        _write_json(output / filename, payload[key])
    audit = verify_p4_c04_freeze(output)
    _write_json(output / "freeze_audit.json", audit)
    return audit


def verify_p4_c04_freeze(root: Path) -> dict[str, Any]:
    root = root.resolve()
    protocol = _read_json(root / "protocol.json")
    selected_plan = _read_json(root / "selected_plan.json")
    workflow_plan = _read_json(root / "workflow_plan.json")
    execution_config = _read_json(root / "execution_config.json")
    asset_inventory = _read_json(root / "asset_inventory.json")
    expected = protocol["frozen_artifact_hashes"]
    checks = {
        "protocol_id": protocol.get("protocol_id") in SUPPORTED_PROTOCOL_IDS,
        "protocol_ready": protocol.get("protocol_ready") is True,
        "execution_gate_consistent": _execution_gate_consistent(protocol),
        "selected_plan_hash": _semantic_hash(selected_plan) == expected["selected_plan"],
        "workflow_plan_hash": _semantic_hash(workflow_plan) == expected["workflow_plan"],
        "execution_config_hash": _semantic_hash(execution_config) == expected["execution_config"],
        "asset_inventory_hash": _semantic_hash(asset_inventory) == expected["asset_inventory"],
        "source_normalization_contract_hash": _normalization_contract_hash_valid(protocol, expected),
        "input_evidence_hashes": all(
            Path(item["path"]).is_file() and _file_hash(Path(item["path"])) == item["sha256"]
            for item in protocol["input_evidence"].values()
        ),
        "implementation_file_hashes": all(
            _file_hash(REPO_ROOT / path) == digest
            for path, digest in protocol["implementation_files"].items()
        ),
        "asset_file_hashes": all(
            Path(item["path"]).is_file() and sha256_file(Path(item["path"])) == item["sha256"]
            for source in asset_inventory["sources"]
            for item in source["files"]
        ),
        "evidence_root_empty": not Path(execution_config["evidence_root"]).exists()
        or not any(Path(execution_config["evidence_root"]).iterdir()),
    }
    try:
        _validate_selected_plan(ResearchPlanningDecision.model_validate(selected_plan))
        _validate_stage_semantics(execution_config)
        checks["semantic_contract"] = True
    except (ValueError, KeyError):
        checks["semantic_contract"] = False
    return {"report_type": "p4_c04_protocol_freeze_audit", "checks": checks, "passed": all(checks.values())}


def _build_asset_inventory(sources: list[Any]) -> dict[str, Any]:
    rows = []
    for source in sources:
        evidence = hash_input_declaration(source)
        frame = gpd.read_file(source.original_path, layer=source.original_layer)
        if frame.crs is None:
            raise ValueError(f"Source has no CRS: {source.source_id}")
        rows.append(
            {
                **evidence,
                "feature_count": len(frame),
                "crs": str(frame.crs),
                "bounds": [round(float(value), 8) for value in frame.total_bounds],
                "empty_geometry_count": int(frame.geometry.is_empty.sum()),
                "null_geometry_count": int(frame.geometry.isna().sum()),
            }
        )
    return {
        "inventory_type": "p4_c04_real_asset_inventory",
        "real_external_data": True,
        "sources": rows,
    }


def _normalization_contract_hash_valid(protocol: dict[str, Any], expected: dict[str, str]) -> bool:
    if protocol.get("protocol_id") != PROTOCOL_ID:
        return True
    reference = (protocol.get("input_evidence") or {}).get("normalization_replay") or {}
    path = Path(str(reference.get("path") or ""))
    if not path.is_file() or "source_normalization_contract" not in expected:
        return False
    replay = _read_json(path)
    return _semantic_hash(replay.get("normalized_contract")) == expected["source_normalization_contract"]


def _validate_asset_overlap(inventory: dict[str, Any]) -> None:
    by_id = {item["source_id"]: item for item in inventory["sources"]}
    boundary = by_id["aoi.venezuela_capital_district"]
    if boundary["feature_count"] != 1 or boundary["empty_geometry_count"] or boundary["null_geometry_count"]:
        raise ValueError("AOI boundary must contain exactly one non-empty geometry")
    for source_id in ("raw.osm.road", "raw.microsoft.road"):
        source = by_id[source_id]
        if source["feature_count"] <= 0 or source["empty_geometry_count"] or source["null_geometry_count"]:
            raise ValueError(f"Road asset is empty or contains invalid geometry placeholders: {source_id}")
        if not _bounds_intersect(source["bounds"], boundary["bounds"]):
            raise ValueError(f"Road asset does not overlap the frozen AOI: {source_id}")


def _validate_selected_plan(plan: ResearchPlanningDecision) -> None:
    if plan.decision != "degraded" or len(plan.tasks) != 1:
        raise ValueError("P4 C04 freeze requires the unchanged degraded single-task formal decision")
    task = plan.tasks[0]
    if (
        task.task_kind != "road"
        or task.source_ids != ["catalog.typhoon.road"]
        or task.algorithm_id != "algo.fusion.road.conflation.v7"
        or task.delivery_state != "degraded"
    ):
        raise ValueError("Selected formal task identity or delivery state changed")


def _validate_stage_semantics(config: dict[str, Any]) -> None:
    stages = config["stages"]
    if len(stages) != 2 or [stage["stage_id"] for stage in stages] != ["osm_provisional", "microsoft_arrival"]:
        raise ValueError("P4 C04 requires exactly the two frozen progressive-delivery stages")
    if "raw.microsoft.road" in stages[0]["active_source_ids"]:
        raise ValueError("Microsoft road must not be active during the provisional stage")
    if stages[0]["delayed_source_ids"] != ["raw.microsoft.road"]:
        raise ValueError("The provisional stage must explicitly record Microsoft as delayed")
    if set(stages[1]["active_source_ids"]) != set(SOURCE_IDS):
        raise ValueError("The arrival stage must activate OSM, Microsoft, and the AOI boundary")
    expected_action = (
        "resume" if config.get("protocol_id") == V1_PROTOCOL_ID else "rerun_with_supersession"
    )
    if stages[1].get("action") != expected_action:
        raise ValueError(f"The arrival stage action must be {expected_action}")
    if config["runtime"]["llm_calls"] != 0 or config["runtime"]["fallback"] != "forbidden":
        raise ValueError("P4 execution must reuse the frozen plan with no LLM calls or fallback")
    if config.get("protocol_id") == PROTOCOL_ID:
        semantics = config.get("source_semantics") or {}
        if (
            semantics.get("normalization_profile") != "normalization.road.microsoft_shapefile.v1"
            or semantics.get("source_feature_id_resolution") != "provider_artifact_fid"
            or semantics.get("road_class_resolution") != "declared_default:road"
            or semantics.get("strict_validation_layer") != "normalized_algorithm_input"
        ):
            raise ValueError("P4 v5 requires the frozen Microsoft normalized input semantic contract")


def _bounds_intersect(left: list[float], right: list[float]) -> bool:
    return left[0] <= right[2] and left[2] >= right[0] and left[1] <= right[3] and left[3] >= right[1]


def _execution_gate_consistent(protocol: dict[str, Any]) -> bool:
    if protocol.get("protocol_id") == V1_PROTOCOL_ID:
        return protocol.get("execution_ready") is False and protocol.get("execution_blockers") == [
            "p4_c04_exact_frozen_plan_runner_not_implemented"
        ]
    runner_contract = protocol.get("runner_contract") or {}
    base_valid = (
        protocol.get("execution_ready") is True
        and protocol.get("execution_blockers") == []
        and runner_contract.get("entrypoint") == "scripts/run_p4_c04_road_e2e.py"
        and runner_contract.get("plan_injection") == "semantic_hash_locked"
        and runner_contract.get("replanning") == "forbidden"
        and runner_contract.get("execution_validation_gate") == "workflow_validator_enforce"
        and runner_contract.get("generic_grounding_probe") == "diagnostic_only"
    )
    if protocol.get("protocol_id") == V2_PROTOCOL_ID:
        return base_valid
    canonical_persistence = runner_contract.get("frozen_plan_persistence") == "canonical_no_derived_fields"
    if protocol.get("protocol_id") == V3_PROTOCOL_ID:
        return base_valid and canonical_persistence
    return (
        base_valid
        and canonical_persistence
        and runner_contract.get("single_source_road_output") == "v7_canonical_contract"
        and runner_contract.get("repair_availability")
        == "product_contract_authorization_intersect_frozen_kg_strategy_nodes"
        and (
            protocol.get("protocol_id") != PROTOCOL_ID
            or (
                runner_contract.get("source_semantic_validation")
                == "normalized_algorithm_input_fail_closed"
                and runner_contract.get("microsoft_identifier_resolution") == "provider_artifact_fid"
                and runner_contract.get("microsoft_road_class_resolution") == "declared_default_road"
            )
        )
    )


def _validate_prior_failure_correction(prior_failure: dict[str, Any]) -> None:
    if (
        prior_failure.get("correction_type") != "non_destructive_evidence_summary_correction"
        or prior_failure.get("protocol_id") != V3_PROTOCOL_ID
        or prior_failure.get("failed_stage_id") != "osm_provisional"
        or prior_failure.get("fusion_algorithm_executions_started") != 1
        or prior_failure.get("fusion_algorithm_executions_completed") != 1
        or prior_failure.get("automatic_retry_performed") is not False
        or prior_failure.get("second_stage_started") is not False
    ):
        raise ValueError("Prior failed attempt does not satisfy the v4 remediation evidence contract")
    preserved = prior_failure.get("preserved_evidence") or {}
    if set(preserved) != {"original_failure_summary", "audit_log", "stage_record"}:
        raise ValueError("Prior failure correction must preserve the original summary, audit, and stage record")
    for item in preserved.values():
        path = Path(str(item.get("path") or ""))
        if not path.is_file() or _file_hash(path) != item.get("sha256"):
            raise ValueError(f"Prior failure correction evidence hash mismatch: {path}")


def _validate_v4_failure(prior_failure: dict[str, Any]) -> None:
    if (
        prior_failure.get("protocol_id") != V4_PROTOCOL_ID
        or prior_failure.get("failed_stage_id") != "microsoft_arrival"
        or prior_failure.get("runtime_runs_created") != 2
        or prior_failure.get("fusion_algorithm_executions_started") != 2
        or prior_failure.get("fusion_algorithm_executions_completed") != 2
        or prior_failure.get("automatic_retry_performed") is not False
        or prior_failure.get("second_stage_started") is not True
    ):
        raise ValueError("Prior failed attempt does not satisfy the v5 remediation evidence contract")


def _validate_normalization_replay(
    replay: dict[str, Any],
    *,
    prior_failure: dict[str, Any],
) -> None:
    contract = replay.get("normalized_contract") or {}
    microsoft = (contract.get("sources") or {}).get("raw.microsoft.road") or {}
    matched = microsoft.get("matched_fields") or {}
    counts = replay.get("execution_counts") or {}
    if (
        replay.get("passed") is not True
        or replay.get("source_protocol_id") != V4_PROTOCOL_ID
        or replay.get("source_failed_run_id") != prior_failure.get("failed_run_id")
        or counts != {"fusion_runs_started": 0, "llm_calls": 0, "provider_network_calls": 0}
        or (contract.get("validation") or {}).get("valid") is not True
        or (contract.get("validation") or {}).get("validated_layer") != "normalized_algorithm_input"
        or microsoft.get("normalization_profile") != "normalization.road.microsoft_shapefile.v1"
        or (matched.get("source_feature_id") or {}).get("derivation") != "provider_artifact_fid"
        or (matched.get("road_class") or {}).get("default_value") != "road"
        or (replay.get("quality_replay") or {}).get("accepted") is not True
    ):
        raise ValueError("Normalization replay does not satisfy the v5 source semantic evidence contract")
    for item in (replay.get("preserved_inputs") or {}).values():
        references = item.values() if isinstance(item, dict) and "path" not in item else [item]
        for reference in references:
            path = Path(str((reference or {}).get("path") or ""))
            if not path.is_file() or _file_hash(path) != (reference or {}).get("sha256"):
                raise ValueError(f"Normalization replay preserved input hash mismatch: {path}")


def _validate_workflow_repair_closure(plan: WorkflowPlan) -> None:
    if plan.product_contract is None:
        raise ValueError("Resolved workflow plan has no product contract")
    authorized = set(plan.product_contract.repair_strategy_ids)
    available = {strategy.strategy_id for strategy in plan.repair_strategies}
    if available != authorized:
        raise ValueError(
            "Resolved workflow repair strategies do not close the product contract: "
            f"authorized={sorted(authorized)}, available={sorted(available)}"
        )


def _input_ref(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": _file_hash(path)}


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _semantic_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_hash(path: Path) -> str:
    return "sha256:" + sha256_file(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze or verify the bounded P4 C04 road execution protocol.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--formal-root", type=Path)
    parser.add_argument("--readiness", type=Path)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--prior-failure", type=Path)
    parser.add_argument("--normalization-replay", type=Path)
    parser.add_argument(
        "--asset-manifest",
        type=Path,
        default=REPO_ROOT / "docs/thesis/manifests/2026-07-20-c02-c04-c06-real-data.json",
    )
    parser.add_argument(
        "--case-manifest",
        type=Path,
        default=REPO_ROOT / "docs/current/research-case-manifest-v1.json",
    )
    args = parser.parse_args()
    if bool(args.output) == bool(args.verify):
        raise ValueError("Specify exactly one of --output or --verify")
    if args.verify:
        audit = verify_p4_c04_freeze(args.verify)
        print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if audit["passed"] else 1
    for name in ("formal_root", "readiness", "evidence_root", "prior_failure", "normalization_replay"):
        if getattr(args, name) is None:
            raise ValueError(f"--{name.replace('_', '-')} is required when freezing")
    payload = build_p4_c04_freeze(
        formal_root=args.formal_root,
        readiness_path=args.readiness,
        asset_manifest_path=args.asset_manifest,
        case_manifest_path=args.case_manifest,
        evidence_root=args.evidence_root,
        prior_failure_path=args.prior_failure,
        normalization_replay_path=args.normalization_replay,
        implementation_commit=_git_head(),
    )
    audit = write_p4_c04_freeze(args.output, payload)
    print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if audit["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
