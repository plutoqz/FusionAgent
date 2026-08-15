from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.inmemory_repository import InMemoryKGRepository
from schemas.research_case_manifest import load_research_case_manifest
from schemas.research_llm_pilot import (
    PilotScheduleItem,
    ResearchLLMPilotSchedule,
    ResearchPlanningDecision,
)
from scripts.freeze_research_formal_protocol import (
    _git_head,
    _load_model_revision_evidence,
    _validate_model_revision_evidence,
)
from scripts.freeze_research_repeated_protocol import (
    _file_hash,
    _read_json,
    _semantic_hash,
    _write_json,
)
from scripts.run_research_llm_pilot import (
    SYSTEM_PROMPT,
    _conservative_token_estimate,
    prepare_research_schedule,
)
from services.research_plan_evaluation import EVALUATOR_ID


PROTOCOL_ID = "fusionagent.planning-repeated-extension-formal.v1"
COMBINED_PROTOCOL_ID = "fusionagent.planning-repeated-combined-formal.v1"
BASE_PROTOCOL_ID = "fusionagent.planning-repeated-formal.v3"
SCHEDULE_SEED = 20260816
EXTENSION_REPLICATES = (4, 5)
TARGET_REPETITIONS = 5
BATCH_TOKEN_BUDGET = 1_200_000
MAX_OUTPUT_TOKENS = 16_384
REQUEST_TIMEOUT_SECONDS = 600
EXPECTED_CALL_COUNT = 36
IMPLEMENTATION_PATHS = (
    "llm/providers/openai_compatible.py",
    "schemas/research_case_manifest.py",
    "schemas/research_llm_pilot.py",
    "scripts/analyze_research_llm_repeated_combined.py",
    "scripts/analyze_research_llm_repeated_formal.py",
    "scripts/freeze_research_repeated_extension_protocol.py",
    "scripts/prepare_research_combined_manual_review.py",
    "scripts/prepare_research_manual_review.py",
    "scripts/run_research_llm_pilot.py",
    "scripts/run_research_llm_repeated_extension_formal.py",
    "services/research_baselines.py",
    "services/research_plan_evaluation.py",
)


def build_extension_freeze(
    *,
    manifest_path: Path,
    base_evidence_root: Path,
    implementation_commit: str,
    model_revision_evidence_path: Path | None = None,
) -> dict[str, Any]:
    manifest = load_research_case_manifest(manifest_path)
    schedule = _build_extension_schedule()
    prepared = prepare_research_schedule(manifest, schedule)
    conservative_bound = sum(
        _conservative_token_estimate(SYSTEM_PROMPT, item["payload"]) + MAX_OUTPUT_TOKENS
        for item in prepared
    )
    revision_evidence = _load_model_revision_evidence(model_revision_evidence_path)
    base_binding = build_base_evidence_binding(base_evidence_root)
    base_checks = verify_base_evidence_binding(base_binding, base_evidence_root)
    blockers = []
    if conservative_bound > BATCH_TOKEN_BUDGET:
        blockers.append("formal_token_budget_below_conservative_bound")
    if revision_evidence is None:
        blockers.append("provider_immutable_model_revision_not_evidenced")
    if not base_checks["passed"]:
        blockers.append("base_v3_evidence_binding_invalid")
    if (
        revision_evidence is not None
        and revision_evidence.get("revision") != base_binding.get("model_revision")
    ):
        blockers.append("model_revision_differs_from_base_v3")
    protocol = {
        "protocol_id": PROTOCOL_ID,
        "combined_protocol_id": COMBINED_PROTOCOL_ID,
        "protocol_status": "blocked_before_formal_execution" if blockers else "frozen",
        "formal_ready": not blockers,
        "formal_blockers": blockers,
        "implementation_commit": implementation_commit,
        "provider": {
            "provider": "deepseek_official",
            "api_protocol": "openai_compatible_chat_completions",
            "base_url_host": "api.deepseek.com",
            "requested_model": "deepseek-v4-flash",
            "required_response_model_exact_match": "deepseek-v4-flash",
            "model_identity_class": "provider_attested_immutable_revision",
            "immutable_model_revision_evidenced": revision_evidence is not None,
            "model_revision": revision_evidence["revision"] if revision_evidence else None,
            "model_revision_evidence_sha256": (
                _semantic_hash(revision_evidence) if revision_evidence else None
            ),
            "api_key_storage": "environment_only",
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
            "cases": list(schedule.cases),
            "llm_conditions": list(schedule.knowledge_conditions),
            "extension_replicates": list(EXTENSION_REPLICATES),
            "extension_call_count": len(schedule.items),
            "schedule_seed": SCHEDULE_SEED,
            "base_protocol_id": BASE_PROTOCOL_ID,
            "base_replicates": [1, 2, 3],
            "target_repetitions": TARGET_REPETITIONS,
            "combined_call_count": 90,
            "extension_scope": "all_cases_and_all_llm_conditions",
            "selective_reruns_allowed": False,
            "prior_incomplete_v2_results_may_be_pooled": False,
            "old_v1_results_may_be_pooled": False,
            "statistical_significance_claim_eligible": False,
        },
        "base_evidence": base_binding,
        "budget": {
            "batch_token_budget": BATCH_TOKEN_BUDGET,
            "conservative_batch_bound": conservative_bound,
            "bound_within_budget": conservative_bound <= BATCH_TOKEN_BUDGET,
            "paid_call_count": len(schedule.items),
        },
        "identities": {
            "kg": InMemoryKGRepository(
                experience_policy="pinned_snapshot"
            ).get_knowledge_identity(),
            "manifest_sha256": _file_hash(manifest_path),
            "output_schema_sha256": _semantic_hash(ResearchPlanningDecision.model_json_schema()),
            "system_prompt_sha256": _semantic_hash(SYSTEM_PROMPT),
            "evaluator_id": EVALUATOR_ID,
            "evaluator_source_sha256": _file_hash(
                REPO_ROOT / "services/research_plan_evaluation.py"
            ),
            "implementation_files": {
                path: _file_hash(REPO_ROOT / path) for path in IMPLEMENTATION_PATHS
            },
            "schedule_sha256": _semantic_hash(schedule.model_dump(mode="json")),
            "prepared_inputs_sha256": _semantic_hash(prepared),
            "base_evidence_binding_sha256": _semantic_hash(base_binding),
        },
        "evidence_policy": {
            "raw_responses_required": True,
            "failed_calls_retained": True,
            "failed_calls_replaced": False,
            "manual_review_not_auto_passed": True,
            "clean_worktree_required": True,
            "base_v3_evidence_read_only": True,
            "prior_v2_evidence_read_only_and_excluded": True,
            "independent_extension_evidence_root_required": True,
        },
        "claim_boundary": (
            "The extension adds repetitions 4 and 5 for every one of the 18 LLM case-condition cells. "
            "Only the bound v3 54-call evidence and this independent 36-call extension may form the "
            "five-repetition analysis. The incomplete v2 batch remains excluded. Descriptive stability "
            "and bounded effects do not establish superiority or broad external validity."
        ),
    }
    return {
        "protocol": protocol,
        "schedule": schedule.model_dump(mode="json"),
        "prepared": prepared,
        "model_revision_evidence": revision_evidence,
        "base_evidence_binding": base_binding,
        "base_evidence_checks": base_checks,
    }


def build_base_evidence_binding(base_root: Path) -> dict[str, Any]:
    audit_path = base_root / "formal_automatic_audit.json"
    audit = _read_json(audit_path)
    if audit.get("protocol_id") != BASE_PROTOCOL_ID:
        raise RuntimeError("Base evidence is not the frozen v3 protocol")
    if audit.get("evidence_integrity_valid") is not True or audit.get(
        "formal_execution_complete"
    ) is not True:
        raise RuntimeError("Base v3 evidence is not complete and integrity-valid")
    gate = audit.get("extension_gate", {})
    if not (
        gate.get("extension_required") is True
        and gate.get("target_repetitions") == TARGET_REPETITIONS
        and gate.get("scope") == "all_cases_and_all_llm_conditions"
        and gate.get("selective_reruns_allowed") is False
    ):
        raise RuntimeError("Base v3 audit does not trigger the frozen full-grid extension gate")
    manifest = audit["evidence_manifest"]
    result_index = sorted(
        (
            {
                "run_id": item["run_id"],
                "size_bytes": item["size_bytes"],
                "sha256": item["sha256"],
            }
            for item in manifest["result_files"]
        ),
        key=lambda item: item["run_id"],
    )
    return {
        "base_protocol_id": BASE_PROTOCOL_ID,
        "base_evidence_root_name": base_root.name,
        "base_call_count": audit["scheduled_call_count"],
        "base_replicates": [1, 2, 3],
        "model": audit["model"],
        "model_revision": audit["model_revision"],
        "formal_automatic_audit_sha256": _raw_file_hash(audit_path),
        "formal_summary_sha256": _raw_file_hash(base_root / "formal_summary.json"),
        "formal_protocol_sha256": _raw_file_hash(base_root / "formal_protocol.json"),
        "schedule_sha256": _raw_file_hash(base_root / "schedule.json"),
        "prepared_inputs_sha256": _raw_file_hash(base_root / "prepared_inputs.json"),
        "evidence_manifest_sha256": _semantic_hash(manifest),
        "result_index_sha256": _semantic_hash(result_index),
        "result_count": len(result_index),
        "extension_gate_reasons_sha256": _semantic_hash(gate["reasons"]),
    }


def verify_base_evidence_binding(binding: dict[str, Any], base_root: Path) -> dict[str, Any]:
    audit_path = base_root / "formal_automatic_audit.json"
    audit = _read_json(audit_path)
    manifest = audit.get("evidence_manifest", {})
    result_index = sorted(
        (
            {
                "run_id": item["run_id"],
                "size_bytes": item["size_bytes"],
                "sha256": item["sha256"],
            }
            for item in manifest.get("result_files", [])
        ),
        key=lambda item: item["run_id"],
    )
    physical_results_valid = len(result_index) == 54 and all(
        _raw_file_hash(base_root / "runs" / item["run_id"] / "result.json")
        == item["sha256"]
        for item in result_index
    )
    checks = {
        "base_protocol_id": audit.get("protocol_id") == binding.get("base_protocol_id") == BASE_PROTOCOL_ID,
        "base_complete": audit.get("evidence_integrity_valid") is True
        and audit.get("formal_execution_complete") is True
        and audit.get("scheduled_call_count") == binding.get("base_call_count") == 54,
        "base_model_identity": audit.get("model") == binding.get("model")
        and audit.get("model_revision") == binding.get("model_revision"),
        "extension_gate_triggered": audit.get("extension_gate", {}).get("extension_required") is True
        and audit.get("extension_gate", {}).get("target_repetitions") == TARGET_REPETITIONS
        and audit.get("extension_gate", {}).get("scope") == "all_cases_and_all_llm_conditions"
        and audit.get("extension_gate", {}).get("selective_reruns_allowed") is False,
        "audit_hash": _raw_file_hash(audit_path)
        == binding.get("formal_automatic_audit_sha256"),
        "summary_hash": _raw_file_hash(base_root / "formal_summary.json")
        == binding.get("formal_summary_sha256"),
        "protocol_hash": _raw_file_hash(base_root / "formal_protocol.json")
        == binding.get("formal_protocol_sha256"),
        "schedule_hash": _raw_file_hash(base_root / "schedule.json")
        == binding.get("schedule_sha256"),
        "prepared_inputs_hash": _raw_file_hash(base_root / "prepared_inputs.json")
        == binding.get("prepared_inputs_sha256"),
        "manifest_hash": _semantic_hash(manifest) == binding.get("evidence_manifest_sha256"),
        "result_index_hash": _semantic_hash(result_index) == binding.get("result_index_sha256")
        and len(result_index) == binding.get("result_count") == 54,
        "physical_result_hashes": physical_results_valid,
        "extension_reasons_hash": _semantic_hash(audit.get("extension_gate", {}).get("reasons"))
        == binding.get("extension_gate_reasons_sha256"),
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return {"checks": checks, "passed": not blockers, "blockers": blockers}


def verify_extension_freeze(root: Path, *, base_evidence_root: Path) -> dict[str, Any]:
    protocol = _read_json(root / "formal_protocol.json")
    schedule = _read_json(root / "formal_schedule.json")
    prepared = _read_json(root / "formal_prepared_inputs.json")
    binding = _read_json(root / "base_evidence_binding.json")
    revision_evidence = _read_json(root / "model_revision_evidence.json")
    manifest_path = REPO_ROOT / "docs/current/research-case-manifest-v1.json"
    base_report = verify_base_evidence_binding(binding, base_evidence_root)
    checks = {
        "protocol_id": protocol.get("protocol_id") == PROTOCOL_ID,
        "schedule_protocol_id": schedule.get("protocol_id") == PROTOCOL_ID,
        "schedule_hash": protocol["identities"]["schedule_sha256"] == _semantic_hash(schedule),
        "prepared_inputs_hash": protocol["identities"]["prepared_inputs_sha256"]
        == _semantic_hash(prepared),
        "base_binding_hash": protocol["identities"]["base_evidence_binding_sha256"]
        == _semantic_hash(binding)
        and protocol.get("base_evidence") == binding,
        "base_evidence_valid": base_report["passed"],
        "manifest_hash": protocol["identities"]["manifest_sha256"] == _file_hash(manifest_path),
        "output_schema_hash": protocol["identities"]["output_schema_sha256"]
        == _semantic_hash(ResearchPlanningDecision.model_json_schema()),
        "evaluator_hash": protocol["identities"]["evaluator_source_sha256"]
        == _file_hash(REPO_ROOT / "services/research_plan_evaluation.py"),
        "implementation_hashes": all(
            expected == _file_hash(REPO_ROOT / path)
            for path, expected in protocol["identities"]["implementation_files"].items()
        ),
        "call_count": len(schedule["items"]) == len(prepared) == EXPECTED_CALL_COUNT,
        "extension_repetitions": schedule.get("replicates") == len(EXTENSION_REPLICATES)
        and {item["replicate"] for item in schedule["items"]} == set(EXTENSION_REPLICATES),
        "unique_extension_run_ids": len({item["run_id"] for item in schedule["items"]})
        == EXPECTED_CALL_COUNT
        and all(item["run_id"].startswith("formal-ext-v1-") for item in schedule["items"]),
        "full_grid_extension": {
            (item["case_id"], item["knowledge_condition"], item["replicate"])
            for item in schedule["items"]
        }
        == {
            (case_id, condition, replicate)
            for case_id in protocol["design"]["cases"]
            for condition in protocol["design"]["llm_conditions"]
            for replicate in EXTENSION_REPLICATES
        },
        "budget_bound": protocol["budget"]["bound_within_budget"] is True,
        "request_timeout_frozen": protocol["generation"].get("request_timeout_seconds")
        == REQUEST_TIMEOUT_SECONDS,
        "zero_recovery_paths": protocol["generation"].get("transport_retries") == 0
        and protocol["generation"].get("semantic_repairs") == 0
        and protocol["generation"].get("json_salvage") == "forbidden"
        and protocol["generation"].get("fallback") == "forbidden",
        "prior_evidence_not_poolable": protocol["design"].get(
            "prior_incomplete_v2_results_may_be_pooled"
        )
        is False
        and protocol["design"].get("old_v1_results_may_be_pooled") is False,
        "immutable_model_revision": _validate_model_revision_evidence(revision_evidence)
        and protocol["provider"]["model_revision"] == revision_evidence["revision"]
        == binding["model_revision"]
        and protocol["provider"]["model_revision_evidence_sha256"]
        == _semantic_hash(revision_evidence),
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return {
        "protocol_id": PROTOCOL_ID,
        "checks": checks,
        "base_evidence_checks": base_report,
        "passed": not blockers,
        "blockers": blockers,
    }


def write_extension_freeze(
    output: Path,
    payload: dict[str, Any],
    *,
    base_evidence_root: Path,
) -> None:
    output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "formal_protocol.json", payload["protocol"])
    _write_json(output / "formal_schedule.json", payload["schedule"])
    _write_json(output / "formal_prepared_inputs.json", payload["prepared"])
    _write_json(output / "model_revision_evidence.json", payload["model_revision_evidence"])
    _write_json(output / "base_evidence_binding.json", payload["base_evidence_binding"])
    _write_json(
        output / "freeze_audit.json",
        verify_extension_freeze(output, base_evidence_root=base_evidence_root),
    )


def _build_extension_schedule() -> ResearchLLMPilotSchedule:
    cases = [f"C{index:02d}" for index in range(1, 7)]
    conditions = ["llm_only", "llm_capability_kg", "llm_full_contract_kg"]
    items = [
        PilotScheduleItem(
            run_id=f"formal-ext-v1-{case_id.lower()}-{condition}-r{replicate}",
            case_id=case_id,
            knowledge_condition=condition,
            replicate=replicate,
        )
        for case_id in cases
        for condition in conditions
        for replicate in EXTENSION_REPLICATES
    ]
    random.Random(SCHEDULE_SEED).shuffle(items)
    return ResearchLLMPilotSchedule(
        protocol_id=PROTOCOL_ID,
        status="draft_preflight",
        cases=cases,
        knowledge_conditions=conditions,
        replicates=len(EXTENSION_REPLICATES),
        items=items,
        metadata={
            "schedule_seed": SCHEDULE_SEED,
            "main_call_count": len(items),
            "replicate_labels": list(EXTENSION_REPLICATES),
            "target_repetitions": TARGET_REPETITIONS,
            "semantic_repairs": 0,
            "transport_retries": 0,
            "fallback": "forbidden",
            "statistical_significance_claim_eligible": False,
        },
    )


def _raw_file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze or verify the 36-call repeated extension protocol.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--base-evidence-root", type=Path, required=True)
    parser.add_argument("--model-revision-evidence", type=Path)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "docs/current/research-case-manifest-v1.json",
    )
    args = parser.parse_args()
    if bool(args.output) == bool(args.verify):
        raise ValueError("Specify exactly one of --output or --verify")
    if args.verify:
        report = verify_extension_freeze(
            args.verify,
            base_evidence_root=args.base_evidence_root,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["passed"] else 1
    payload = build_extension_freeze(
        manifest_path=args.manifest,
        base_evidence_root=args.base_evidence_root,
        implementation_commit=_git_head(),
        model_revision_evidence_path=args.model_revision_evidence,
    )
    write_extension_freeze(
        args.output,
        payload,
        base_evidence_root=args.base_evidence_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
