from __future__ import annotations

import argparse
import json
import random
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
    FORBIDDEN_PLANNER_KEYS,
    SYSTEM_PROMPT,
    _conservative_token_estimate,
    _nested_keys,
    _write_json,
    execute_pilot,
)
from services.research_baselines import BaselineGroup, CanonicalContextFactory
from services.research_contract_aware_planning import (
    METHOD_B_ID,
    build_contract_aware_projection,
)
from services.research_plan_evaluation import EVALUATOR_ID
from services.research_manifest_validation import validate_manifest_crosswalk


PROTOCOL_ID = "fusionagent.method-b-heldout-formal.v1"
SCHEDULE_SEED = 20260816
REPLICATES = 3
MAX_OUTPUT_TOKENS = 16384
REQUEST_TIMEOUT_SECONDS = 600
BATCH_TOKEN_BUDGET = 1700000
CONDITIONS = [
    "llm_only",
    "llm_full_contract_kg",
    "task_conditioned_contract_aware_kg",
]


def prepare_formal_inputs(manifest_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = load_research_case_manifest(manifest_path)
    if manifest.status != "frozen":
        raise RuntimeError("Held-out manifest must be frozen before formal preparation.")
    repository = InMemoryKGRepository(experience_policy="pinned_snapshot")
    failures = validate_manifest_crosswalk(manifest, repository)
    if failures:
        raise RuntimeError(f"Held-out manifest KG crosswalk is not closed: {failures}")
    cases = {case.case_id: case for case in manifest.cases}
    items = [
        {
            "run_id": f"formal-heldout-{case_id.lower()}-{condition}-r{replicate}",
            "case_id": case_id,
            "knowledge_condition": condition,
            "replicate": replicate,
            "input_variant": PROTOCOL_ID,
        }
        for case_id in sorted(cases)
        for condition in CONDITIONS
        for replicate in range(1, REPLICATES + 1)
    ]
    random.Random(SCHEDULE_SEED).shuffle(items)
    factory = CanonicalContextFactory(repository)
    prepared = []
    for item in items:
        case = cases[item["case_id"]]
        if item["knowledge_condition"] == "task_conditioned_contract_aware_kg":
            projection = build_contract_aware_projection(case, repository)
        else:
            projection = factory.project(
                factory.build(case),
                BaselineGroup(item["knowledge_condition"]),
            )
        leaked = sorted(FORBIDDEN_PLANNER_KEYS & set(_nested_keys(projection.payload)))
        if leaked:
            raise RuntimeError(f"{item['run_id']} planning input contains forbidden gold keys: {leaked}")
        prepared.append(
            {
                "schedule": item,
                "input_hash": projection.input_hash,
                "allowed_top_level_fields": projection.allowed_top_level_fields,
                "forbidden_top_level_fields": projection.forbidden_top_level_fields,
                "payload": projection.payload,
            }
        )
    schedule = {
        "protocol_id": PROTOCOL_ID,
        "status": "frozen",
        "schedule_seed": SCHEDULE_SEED,
        "cases": sorted(cases),
        "knowledge_conditions": CONDITIONS,
        "replicates": REPLICATES,
        "items": items,
        "metadata": {
            "fallback": "forbidden",
            "transport_retries": 0,
            "semantic_repairs": 0,
            "development_cases_excluded": ["C01", "C02", "C03", "C04", "C05", "C06"],
        },
    }
    return schedule, prepared


def build_freeze(
    *,
    manifest_path: Path,
    implementation_commit: str,
    model_revision_evidence_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    schedule, prepared = prepare_formal_inputs(manifest_path)
    evidence = json.loads(model_revision_evidence_path.read_text(encoding="utf-8"))
    conservative_bound = sum(
        _conservative_token_estimate(SYSTEM_PROMPT, item["payload"]) + MAX_OUTPUT_TOKENS
        for item in prepared
    )
    if conservative_bound > BATCH_TOKEN_BUDGET:
        raise RuntimeError(
            f"Formal held-out conservative token bound exceeds budget: {conservative_bound} > {BATCH_TOKEN_BUDGET}"
        )
    protocol = {
        "protocol_id": PROTOCOL_ID,
        "protocol_status": "frozen",
        "formal_ready": True,
        "implementation_commit": implementation_commit,
        "method_id": METHOD_B_ID,
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
            "knowledge_conditions": CONDITIONS,
            "repetitions": REPLICATES,
            "call_count": len(schedule["items"]),
            "schedule_seed": SCHEDULE_SEED,
            "development_cases_excluded": schedule["metadata"]["development_cases_excluded"],
            "statistical_significance_claim_eligible": False,
            "manual_review_required": True,
        },
        "budget": {
            "batch_token_budget": BATCH_TOKEN_BUDGET,
            "conservative_batch_bound": conservative_bound,
            "bound_within_budget": True,
            "paid_call_count": len(schedule["items"]),
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
            "kg_identity": InMemoryKGRepository(experience_policy="pinned_snapshot").get_knowledge_identity(),
        },
        "evidence_policy": {
            "raw_responses_required": True,
            "failed_calls_retained": True,
            "failed_calls_replaced": False,
            "manual_review_not_auto_passed": True,
            "clean_worktree_required": True,
        },
        "claim_boundary": (
            "Held-out planning validation of method B against LLM-only and raw/full-contract KG. "
            "No superiority or statistical significance claim is eligible before manual review and audit."
        ),
    }
    return protocol, schedule, prepared


def verify_freeze(root: Path, manifest_path: Path) -> dict[str, Any]:
    protocol = _read_json(root / "formal_protocol.json")
    schedule = _read_json(root / "schedule.json")
    prepared = _read_json(root / "prepared_inputs.json")
    checks = {
        "protocol_frozen": protocol.get("protocol_status") == "frozen" and protocol.get("formal_ready") is True,
        "manifest_frozen": load_research_case_manifest(manifest_path).status == "frozen",
        "call_grid": len(schedule.get("items", [])) == 54 and len(prepared) == 54,
        "condition_grid": set(schedule.get("knowledge_conditions", [])) == set(CONDITIONS),
        "replicate_grid": {item["replicate"] for item in schedule.get("items", [])} == {1, 2, 3},
        "unique_run_ids": len({item["run_id"] for item in schedule.get("items", [])}) == 54,
        "schedule_hash": protocol["identities"]["schedule_sha256"] == semantic_hash(schedule),
        "prepared_inputs_hash": protocol["identities"]["prepared_inputs_sha256"] == semantic_hash(prepared),
        "manifest_hash": protocol["identities"]["manifest_sha256"] == _file_hash(manifest_path),
        "output_schema_hash": protocol["identities"]["output_schema_sha256"]
        == semantic_hash(ResearchPlanningDecision.model_json_schema()),
        "evaluator_hash": protocol["identities"]["evaluator_source_sha256"]
        == _file_hash(REPO_ROOT / "services/research_plan_evaluation.py"),
        "method_hash": protocol["identities"]["method_source_sha256"]
        == _file_hash(REPO_ROOT / "services/research_contract_aware_planning.py"),
        "budget_bound": protocol["budget"]["bound_within_budget"] is True,
    }
    return {"protocol_id": PROTOCOL_ID, "checks": checks, "passed": all(checks.values())}


def run_formal(root: Path, *, manifest_path: Path, model_revision_evidence_path: Path, execute: bool) -> int:
    if root.exists():
        raise RuntimeError(f"Refusing to overwrite formal held-out evidence root: {root}")
    root.mkdir(parents=True)
    protocol, schedule, prepared = build_freeze(
        manifest_path=manifest_path,
        implementation_commit=_git_head(),
        model_revision_evidence_path=model_revision_evidence_path,
    )
    _write_json(root / "formal_protocol.json", protocol)
    _write_json(root / "schedule.json", schedule)
    _write_json(root / "prepared_inputs.json", prepared)
    shutil.copy2(model_revision_evidence_path, root / "model_revision_evidence.json")
    _write_json(root / "freeze_audit.json", verify_freeze(root, manifest_path))
    if not execute:
        _write_json(root / "preflight.json", {"status": "formal_ready", "paid_provider_calls_made": 0})
        return 0
    results = execute_pilot(
        prepared,
        root,
        pilot_scope="method_b_heldout_formal",
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
            "comparative_claim_status": "pending_manual_review_and_analysis",
        },
    )
    return 0


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()


def _file_hash(path: Path) -> str:
    import hashlib

    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze and execute the method B held-out formal protocol.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--model-revision-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    return run_formal(
        args.output,
        manifest_path=args.manifest,
        model_revision_evidence_path=args.model_revision_evidence,
        execute=args.execute,
    )


if __name__ == "__main__":
    raise SystemExit(main())
