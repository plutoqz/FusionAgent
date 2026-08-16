from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.inmemory_repository import InMemoryKGRepository
from kg.knowledge_release import semantic_hash
from schemas.research_case_manifest import load_research_case_manifest
from schemas.research_llm_pilot import ResearchPlanningDecision
from scripts.run_research_llm_pilot import (
    SYSTEM_PROMPT,
    _conservative_token_estimate,
    _write_json,
    execute_pilot,
)
from scripts.run_research_method_b_formal import (
    MAX_OUTPUT_TOKENS,
    PROTOCOL_ID as BASE_PROTOCOL_ID,
    REPLICATES,
    REQUEST_TIMEOUT_SECONDS,
    prepare_formal_inputs,
)
from services.research_contract_aware_planning import METHOD_B_ID
from services.research_plan_evaluation import EVALUATOR_ID


PROTOCOL_ID = "fusionagent.method-b-heldout-formal-repair.v1"
METHOD_B_CONDITION = "task_conditioned_contract_aware_kg"
BASELINE_CONDITIONS = {"llm_only", "llm_full_contract_kg"}
BATCH_TOKEN_BUDGET = 600000


def prepare_repair_inputs(
    manifest_path: Path,
    base_evidence_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    manifest = load_research_case_manifest(manifest_path)
    if manifest.status != "frozen":
        raise RuntimeError("Held-out manifest must remain frozen for repair validation.")

    base_protocol = _read_json(base_evidence_root / "formal_protocol.json")
    base_schedule = _read_json(base_evidence_root / "schedule.json")
    base_prepared = _read_json(base_evidence_root / "prepared_inputs.json")
    if base_protocol.get("protocol_id") != BASE_PROTOCOL_ID:
        raise RuntimeError("Base evidence root is not the frozen method B held-out protocol.")
    if base_protocol["identities"]["schedule_sha256"] != semantic_hash(base_schedule):
        raise RuntimeError("Base schedule no longer matches its frozen protocol hash.")
    if base_protocol["identities"]["prepared_inputs_sha256"] != semantic_hash(base_prepared):
        raise RuntimeError("Base prepared inputs no longer match their frozen protocol hash.")

    _, current_full_prepared = prepare_formal_inputs(manifest_path)
    base_by_cell = {_cell_key(item): item for item in base_prepared}
    current_by_cell = {_cell_key(item): item for item in current_full_prepared}
    expected_baseline_cells = {
        (case.case_id, condition, replicate)
        for case in manifest.cases
        for condition in BASELINE_CONDITIONS
        for replicate in range(1, REPLICATES + 1)
    }
    if set(base_by_cell).intersection(expected_baseline_cells) != expected_baseline_cells:
        raise RuntimeError("Base evidence is missing one or more frozen baseline cells.")
    if set(current_by_cell).intersection(expected_baseline_cells) != expected_baseline_cells:
        raise RuntimeError("Current preparation is missing one or more baseline cells.")
    changed_baselines = [
        cell
        for cell in sorted(expected_baseline_cells)
        if base_by_cell[cell]["input_hash"] != current_by_cell[cell]["input_hash"]
        or semantic_hash(base_by_cell[cell]["payload"])
        != semantic_hash(current_by_cell[cell]["payload"])
    ]
    if changed_baselines:
        raise RuntimeError(f"Frozen baseline inputs changed before repair validation: {changed_baselines}")

    selected = [
        item
        for item in current_full_prepared
        if item["schedule"]["knowledge_condition"] == METHOD_B_CONDITION
    ]
    prepared = []
    for item in selected:
        copied = json.loads(json.dumps(item))
        case_id = copied["schedule"]["case_id"]
        replicate = copied["schedule"]["replicate"]
        copied["schedule"].update(
            {
                "run_id": f"formal-heldout-repair-{case_id.lower()}-method-b-r{replicate}",
                "input_variant": PROTOCOL_ID,
            }
        )
        prepared.append(copied)

    base_result_files = sorted((base_evidence_root / "runs").glob("*/result.json"))
    base_results = [_read_json(path) for path in base_result_files]
    base_results_by_run = {item["run_id"]: item for item in base_results}
    baseline_run_ids = {
        base_by_cell[cell]["schedule"]["run_id"] for cell in expected_baseline_cells
    }
    if not baseline_run_ids.issubset(base_results_by_run):
        raise RuntimeError("Base evidence is missing one or more baseline result files.")
    if not all(base_results_by_run[run_id].get("success") is True for run_id in baseline_run_ids):
        raise RuntimeError("Base baseline evidence contains unsuccessful calls and cannot be reused.")

    schedule_items = [item["schedule"] for item in prepared]
    schedule = {
        "protocol_id": PROTOCOL_ID,
        "status": "frozen",
        "cases": sorted(case.case_id for case in manifest.cases),
        "knowledge_conditions": [METHOD_B_CONDITION],
        "replicates": REPLICATES,
        "items": schedule_items,
        "metadata": {
            "fallback": "forbidden",
            "transport_retries": 0,
            "semantic_repairs": 0,
            "base_protocol_id": BASE_PROTOCOL_ID,
            "base_baseline_calls_reused_read_only": len(baseline_run_ids),
            "development_cases_excluded": ["C01", "C02", "C03", "C04", "C05", "C06"],
        },
    }
    binding = {
        "binding_type": "read_only_baseline_reuse",
        "base_evidence_root": str(base_evidence_root.resolve()),
        "base_protocol_id": BASE_PROTOCOL_ID,
        "base_implementation_commit": base_protocol["implementation_commit"],
        "base_protocol_file_sha256": _file_hash(base_evidence_root / "formal_protocol.json"),
        "base_schedule_file_sha256": _file_hash(base_evidence_root / "schedule.json"),
        "base_prepared_inputs_file_sha256": _file_hash(base_evidence_root / "prepared_inputs.json"),
        "baseline_conditions": sorted(BASELINE_CONDITIONS),
        "baseline_call_count": len(baseline_run_ids),
        "baseline_input_hashes_unchanged": True,
        "baseline_result_file_hashes": {
            run_id: _file_hash(base_evidence_root / "runs" / run_id / "result.json")
            for run_id in sorted(baseline_run_ids)
        },
    }
    return schedule, prepared, binding


def build_freeze(
    *,
    manifest_path: Path,
    base_evidence_root: Path,
    implementation_commit: str,
    model_revision_evidence_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    schedule, prepared, binding = prepare_repair_inputs(manifest_path, base_evidence_root)
    evidence = _read_json(model_revision_evidence_path)
    conservative_bound = sum(
        _conservative_token_estimate(SYSTEM_PROMPT, item["payload"]) + MAX_OUTPUT_TOKENS
        for item in prepared
    )
    if conservative_bound > BATCH_TOKEN_BUDGET:
        raise RuntimeError(
            f"Repair conservative token bound exceeds budget: {conservative_bound} > {BATCH_TOKEN_BUDGET}"
        )
    protocol = {
        "protocol_id": PROTOCOL_ID,
        "protocol_status": "frozen",
        "formal_ready": True,
        "implementation_commit": implementation_commit,
        "method_id": METHOD_B_ID,
        "repair": {
            "trigger": "H06 method B returned reject with executable tasks in all three original calls",
            "mechanism": "unsupported scenarios compile to reject-only context with no task rows",
            "case_specific_logic_added": False,
            "all_method_b_cells_rerun": True,
            "post_heldout_intervention": True,
        },
        "provider": {
            "provider": "deepseek_official",
            "model": "deepseek-v4-flash",
            "model_revision": evidence["revision"],
            "model_revision_evidence_sha256": semantic_hash(evidence),
            "base_url_host": "api.deepseek.com",
        },
        "generation": {
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "max_output_tokens": MAX_OUTPUT_TOKENS,
            "request_timeout_seconds": REQUEST_TIMEOUT_SECONDS,
            "transport_retries": 0,
            "semantic_repairs": 0,
            "json_salvage": "forbidden",
            "fallback": "forbidden",
        },
        "design": {
            "cases": schedule["cases"],
            "knowledge_conditions": [METHOD_B_CONDITION],
            "repetitions": REPLICATES,
            "new_paid_call_count": len(prepared),
            "reused_read_only_baseline_calls": binding["baseline_call_count"],
            "manual_review_required": True,
            "statistical_significance_claim_eligible": False,
        },
        "budget": {
            "batch_token_budget": BATCH_TOKEN_BUDGET,
            "conservative_batch_bound": conservative_bound,
            "bound_within_budget": True,
            "paid_call_count": len(prepared),
        },
        "identities": {
            "manifest_sha256": _file_hash(manifest_path),
            "output_schema_sha256": semantic_hash(ResearchPlanningDecision.model_json_schema()),
            "system_prompt_sha256": semantic_hash(SYSTEM_PROMPT),
            "evaluator_id": EVALUATOR_ID,
            "evaluator_source_sha256": _file_hash(REPO_ROOT / "services/research_plan_evaluation.py"),
            "method_source_sha256": _file_hash(REPO_ROOT / "services/research_contract_aware_planning.py"),
            "schedule_sha256": semantic_hash(schedule),
            "prepared_inputs_sha256": semantic_hash(prepared),
            "baseline_binding_sha256": semantic_hash(binding),
            "kg_identity": InMemoryKGRepository(
                experience_policy="pinned_snapshot"
            ).get_knowledge_identity(),
        },
        "evidence_policy": {
            "raw_responses_required": True,
            "failed_calls_retained": True,
            "failed_calls_replaced": False,
            "base_evidence_mutation_forbidden": True,
            "manual_review_not_auto_passed": True,
            "clean_worktree_required": True,
        },
        "claim_boundary": (
            "Post-held-out repair validation with read-only frozen baselines. It can validate the generic "
            "contract fix and update comparative planning evidence, but is not a pristine independent "
            "confirmatory test because H06 triggered the intervention. Superiority remains ineligible before "
            "blinded manual review, stability audit, and a new independent confirmation set if claimed as formal."
        ),
    }
    return protocol, schedule, prepared, binding


def verify_freeze(root: Path, manifest_path: Path) -> dict[str, Any]:
    protocol = _read_json(root / "formal_protocol.json")
    schedule = _read_json(root / "schedule.json")
    prepared = _read_json(root / "prepared_inputs.json")
    binding = _read_json(root / "baseline_binding.json")
    base_root = Path(binding["base_evidence_root"])
    checks = {
        "protocol_frozen": protocol.get("protocol_status") == "frozen"
        and protocol.get("formal_ready") is True,
        "manifest_frozen": load_research_case_manifest(manifest_path).status == "frozen",
        "repair_call_grid": len(schedule.get("items", [])) == 18 and len(prepared) == 18,
        "method_b_only": schedule.get("knowledge_conditions") == [METHOD_B_CONDITION],
        "replicate_grid": {item["replicate"] for item in schedule.get("items", [])} == {1, 2, 3},
        "unique_run_ids": len({item["run_id"] for item in schedule.get("items", [])}) == 18,
        "schedule_hash": protocol["identities"]["schedule_sha256"] == semantic_hash(schedule),
        "prepared_inputs_hash": protocol["identities"]["prepared_inputs_sha256"]
        == semantic_hash(prepared),
        "baseline_binding_hash": protocol["identities"]["baseline_binding_sha256"]
        == semantic_hash(binding),
        "base_protocol_unchanged": binding["base_protocol_file_sha256"]
        == _file_hash(base_root / "formal_protocol.json"),
        "base_schedule_unchanged": binding["base_schedule_file_sha256"]
        == _file_hash(base_root / "schedule.json"),
        "base_prepared_inputs_unchanged": binding["base_prepared_inputs_file_sha256"]
        == _file_hash(base_root / "prepared_inputs.json"),
        "base_result_files_unchanged": all(
            expected == _file_hash(base_root / "runs" / run_id / "result.json")
            for run_id, expected in binding["baseline_result_file_hashes"].items()
        ),
        "baseline_input_hashes_unchanged": binding["baseline_input_hashes_unchanged"] is True,
        "manifest_hash": protocol["identities"]["manifest_sha256"] == _file_hash(manifest_path),
        "output_schema_hash": protocol["identities"]["output_schema_sha256"]
        == semantic_hash(ResearchPlanningDecision.model_json_schema()),
        "evaluator_hash": protocol["identities"]["evaluator_source_sha256"]
        == _file_hash(REPO_ROOT / "services/research_plan_evaluation.py"),
        "method_hash": protocol["identities"]["method_source_sha256"]
        == _file_hash(REPO_ROOT / "services/research_contract_aware_planning.py"),
        "budget_bound": protocol["budget"]["bound_within_budget"] is True,
        "post_heldout_boundary_recorded": protocol["repair"]["post_heldout_intervention"] is True,
    }
    return {"protocol_id": PROTOCOL_ID, "checks": checks, "passed": all(checks.values())}


def run_formal(
    root: Path,
    *,
    manifest_path: Path,
    base_evidence_root: Path,
    model_revision_evidence_path: Path,
    execute: bool,
) -> int:
    if root.exists():
        raise RuntimeError(f"Refusing to overwrite repair evidence root: {root}")
    root.mkdir(parents=True)
    protocol, schedule, prepared, binding = build_freeze(
        manifest_path=manifest_path,
        base_evidence_root=base_evidence_root,
        implementation_commit=_git_head(),
        model_revision_evidence_path=model_revision_evidence_path,
    )
    _write_json(root / "formal_protocol.json", protocol)
    _write_json(root / "schedule.json", schedule)
    _write_json(root / "prepared_inputs.json", prepared)
    _write_json(root / "baseline_binding.json", binding)
    shutil.copy2(model_revision_evidence_path, root / "model_revision_evidence.json")
    _write_json(root / "freeze_audit.json", verify_freeze(root, manifest_path))
    if not execute:
        _write_json(root / "preflight.json", {"status": "formal_ready", "paid_provider_calls_made": 0})
        return 0
    results = execute_pilot(
        prepared,
        root,
        pilot_scope="method_b_heldout_formal_repair",
        claim_eligible=False,
        protocol_id=PROTOCOL_ID,
        model_revision=protocol["provider"]["model_revision"],
    )
    _write_json(
        root / "formal_summary.json",
        {
            "status": "completed" if len(results) == len(prepared) else "completed_with_observed_failures",
            "scheduled_calls": len(prepared),
            "executed_calls": len(results),
            "successful_calls": sum(item.get("success") is True for item in results),
            "failed_calls": sum(item.get("success") is not True for item in results),
            "manual_review_status": "pending",
            "comparative_claim_status": "pending_merged_analysis_and_manual_review",
        },
    )
    return 0


def _cell_key(item: dict[str, Any]) -> tuple[str, str, int]:
    schedule = item["schedule"]
    return schedule["case_id"], schedule["knowledge_condition"], schedule["replicate"]


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze and execute the 18-call method B repair protocol.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--base-evidence-root", type=Path, required=True)
    parser.add_argument("--model-revision-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    return run_formal(
        args.output,
        manifest_path=args.manifest,
        base_evidence_root=args.base_evidence_root,
        model_revision_evidence_path=args.model_revision_evidence,
        execute=args.execute,
    )


if __name__ == "__main__":
    raise SystemExit(main())
