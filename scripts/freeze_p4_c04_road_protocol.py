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


CASE_ID = "C04"
CONDITION = "llm_full_contract_kg"
RUN_ID = "formal-c04-llm_full_contract_kg-r1"
SOURCE_IDS = ("raw.osm.road", "raw.microsoft.road", "aoi.venezuela_capital_district")
LEGACY_PROTOCOL_ID = "fusionagent.p4.c04-road-e2e.v1"
PROTOCOL_ID = "fusionagent.p4.c04-road-e2e.v2"


def build_p4_c04_freeze(
    *,
    formal_root: Path,
    readiness_path: Path,
    asset_manifest_path: Path,
    case_manifest_path: Path,
    evidence_root: Path,
    implementation_commit: str,
) -> dict[str, Any]:
    formal_root = formal_root.resolve()
    readiness_path = readiness_path.resolve()
    asset_manifest_path = asset_manifest_path.resolve()
    case_manifest_path = case_manifest_path.resolve()
    evidence_root = evidence_root.resolve()

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
    resolution = ready_rows[0]["resolution"]
    workflow_plan = WorkflowPlan.model_validate(resolution["workflow_plan"])
    repository = InMemoryKGRepository(experience_policy="pinned_snapshot")
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
            "run_id": "p4-c04-road-caracas-r1",
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
        ],
    }
    _validate_stage_semantics(execution_config)

    implementation_files = {
        path: _file_hash(REPO_ROOT / path)
        for path in (
            "services/research_plan_runtime_adapter.py",
            "scripts/audit_p4_planning_e2e_readiness.py",
            "scripts/freeze_p4_c04_road_protocol.py",
            "scripts/run_p4_c04_road_e2e.py",
            "services/agent_run_service.py",
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
        },
        "frozen_artifact_hashes": {
            "selected_plan": _semantic_hash(selected_plan.model_dump(mode="json")),
            "workflow_plan": _semantic_hash(workflow_plan.model_dump(mode="json")),
            "execution_config": _semantic_hash(execution_config),
            "asset_inventory": _semantic_hash(asset_inventory),
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
        "protocol_id": protocol.get("protocol_id") in {LEGACY_PROTOCOL_ID, PROTOCOL_ID},
        "protocol_ready": protocol.get("protocol_ready") is True,
        "execution_gate_consistent": _execution_gate_consistent(protocol),
        "selected_plan_hash": _semantic_hash(selected_plan) == expected["selected_plan"],
        "workflow_plan_hash": _semantic_hash(workflow_plan) == expected["workflow_plan"],
        "execution_config_hash": _semantic_hash(execution_config) == expected["execution_config"],
        "asset_inventory_hash": _semantic_hash(asset_inventory) == expected["asset_inventory"],
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
        "resume" if config.get("protocol_id") == LEGACY_PROTOCOL_ID else "rerun_with_supersession"
    )
    if stages[1].get("action") != expected_action:
        raise ValueError(f"The arrival stage action must be {expected_action}")
    if config["runtime"]["llm_calls"] != 0 or config["runtime"]["fallback"] != "forbidden":
        raise ValueError("P4 execution must reuse the frozen plan with no LLM calls or fallback")


def _bounds_intersect(left: list[float], right: list[float]) -> bool:
    return left[0] <= right[2] and left[2] >= right[0] and left[1] <= right[3] and left[3] >= right[1]


def _execution_gate_consistent(protocol: dict[str, Any]) -> bool:
    if protocol.get("protocol_id") == LEGACY_PROTOCOL_ID:
        return protocol.get("execution_ready") is False and protocol.get("execution_blockers") == [
            "p4_c04_exact_frozen_plan_runner_not_implemented"
        ]
    runner_contract = protocol.get("runner_contract") or {}
    return (
        protocol.get("execution_ready") is True
        and protocol.get("execution_blockers") == []
        and runner_contract.get("entrypoint") == "scripts/run_p4_c04_road_e2e.py"
        and runner_contract.get("plan_injection") == "semantic_hash_locked"
        and runner_contract.get("replanning") == "forbidden"
        and runner_contract.get("execution_validation_gate") == "workflow_validator_enforce"
        and runner_contract.get("generic_grounding_probe") == "diagnostic_only"
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
    for name in ("formal_root", "readiness", "evidence_root"):
        if getattr(args, name) is None:
            raise ValueError(f"--{name.replace('_', '-')} is required when freezing")
    payload = build_p4_c04_freeze(
        formal_root=args.formal_root,
        readiness_path=args.readiness,
        asset_manifest_path=args.asset_manifest,
        case_manifest_path=args.case_manifest,
        evidence_root=args.evidence_root,
        implementation_commit=_git_head(),
    )
    audit = write_p4_c04_freeze(args.output, payload)
    print(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if audit["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
