from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.inmemory_repository import InMemoryKGRepository
from schemas.research_case_manifest import load_research_case_manifest
from schemas.research_llm_pilot import (
    ResearchLLMPilotSchedule,
    ResearchPlanningDecision,
    build_research_llm_repeated_schedule,
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


PROTOCOL_ID = "fusionagent.planning-repeated-formal.v3"
SCHEDULE_SEED = 20260815
REPLICATES = 3
BATCH_TOKEN_BUDGET = 1_700_000
MAX_OUTPUT_TOKENS = 16_384
REQUEST_TIMEOUT_SECONDS = 600
PRIOR_INCOMPLETE_PROTOCOL_ID = "fusionagent.planning-repeated-formal.v2"
IMPLEMENTATION_PATHS = (
    "llm/providers/openai_compatible.py",
    "schemas/research_case_manifest.py",
    "schemas/research_llm_pilot.py",
    "scripts/freeze_research_repeated_protocol_v3.py",
    "scripts/run_research_llm_pilot.py",
    "scripts/run_research_llm_repeated_formal_v3.py",
    "services/research_baselines.py",
    "services/research_plan_evaluation.py",
)


def build_repeated_freeze_v3(
    *,
    manifest_path: Path,
    implementation_commit: str,
    model_revision_evidence_path: Path | None = None,
) -> dict[str, Any]:
    manifest = load_research_case_manifest(manifest_path)
    schedule = _build_v3_schedule()
    prepared = prepare_research_schedule(manifest, schedule)
    conservative_bound = sum(
        _conservative_token_estimate(SYSTEM_PROMPT, item["payload"]) + MAX_OUTPUT_TOKENS
        for item in prepared
    )
    revision_evidence = _load_model_revision_evidence(model_revision_evidence_path)
    blockers = []
    if conservative_bound > BATCH_TOKEN_BUDGET:
        blockers.append("formal_token_budget_below_conservative_bound")
    if revision_evidence is None:
        blockers.append("provider_immutable_model_revision_not_evidenced")
    protocol = {
        "protocol_id": PROTOCOL_ID,
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
            "model_identity_class": (
                "provider_attested_immutable_revision"
                if revision_evidence is not None
                else "provider_reported_exact_id"
            ),
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
            "llm_repetitions": REPLICATES,
            "llm_call_count": len(schedule.items),
            "schedule_seed": SCHEDULE_SEED,
            "prior_incomplete_protocol_id": PRIOR_INCOMPLETE_PROTOCOL_ID,
            "prior_incomplete_results_may_be_pooled": False,
            "old_v1_results_may_be_pooled": False,
            "stability_analysis_eligible": True,
            "statistical_significance_claim_eligible": False,
        },
        "replication_policy": {
            "initial_repetitions": REPLICATES,
            "extension_repetitions": 5,
            "extension_scope": "all_cases_and_all_llm_conditions",
            "extend_if_any": [
                "any_cell_has_observed_provider_or_schema_failure",
                "any_cell_has_more_than_one_plan_structure_signature",
                "any_cell_automatic_score_range_gte_0.25",
            ],
            "selective_reruns_for_failed_or_low_scoring_cells": "forbidden",
            "extension_requires_new_protocol_and_budget_freeze": True,
        },
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
        },
        "evidence_policy": {
            "raw_responses_required": True,
            "failed_calls_retained": True,
            "failed_calls_replaced": False,
            "manual_review_not_auto_passed": True,
            "clean_worktree_required": True,
            "prior_v2_evidence_read_only": True,
        },
        "claim_boundary": (
            "This is a full independent rerun after an incomplete v2 batch. Results are not pooled with v2. "
            "Three repetitions characterize within-case planning stability and bounded effect estimates only."
        ),
    }
    return {
        "protocol": protocol,
        "schedule": schedule.model_dump(mode="json"),
        "prepared": prepared,
        "model_revision_evidence": revision_evidence,
    }


def verify_repeated_freeze_v3(root: Path) -> dict[str, Any]:
    protocol = _read_json(root / "formal_protocol.json")
    schedule = _read_json(root / "formal_schedule.json")
    prepared = _read_json(root / "formal_prepared_inputs.json")
    evidence_path = root / "model_revision_evidence.json"
    revision_evidence = _read_json(evidence_path) if evidence_path.exists() else None
    manifest_path = REPO_ROOT / "docs/current/research-case-manifest-v1.json"
    expected_count = 6 * 3 * REPLICATES
    checks = {
        "protocol_id": protocol.get("protocol_id") == PROTOCOL_ID,
        "schedule_protocol_id": schedule.get("protocol_id") == PROTOCOL_ID,
        "schedule_hash": protocol["identities"]["schedule_sha256"] == _semantic_hash(schedule),
        "prepared_inputs_hash": (
            protocol["identities"]["prepared_inputs_sha256"] == _semantic_hash(prepared)
        ),
        "manifest_hash": protocol["identities"]["manifest_sha256"] == _file_hash(manifest_path),
        "output_schema_hash": (
            protocol["identities"]["output_schema_sha256"]
            == _semantic_hash(ResearchPlanningDecision.model_json_schema())
        ),
        "evaluator_hash": (
            protocol["identities"]["evaluator_source_sha256"]
            == _file_hash(REPO_ROOT / "services/research_plan_evaluation.py")
        ),
        "implementation_hashes": all(
            expected == _file_hash(REPO_ROOT / path)
            for path, expected in protocol["identities"]["implementation_files"].items()
        ),
        "call_count": len(schedule["items"]) == len(prepared) == expected_count,
        "three_complete_repetitions": (
            schedule.get("replicates") == REPLICATES
            and {item["replicate"] for item in schedule["items"]} == {1, 2, 3}
        ),
        "unique_v3_run_ids": (
            len({item["run_id"] for item in schedule["items"]}) == expected_count
            and all(item["run_id"].startswith("formal-v3-") for item in schedule["items"])
        ),
        "budget_bound": protocol["budget"]["bound_within_budget"] is True,
        "request_timeout_frozen": (
            protocol["generation"].get("request_timeout_seconds") == REQUEST_TIMEOUT_SECONDS
        ),
        "prior_v2_not_poolable": (
            protocol["design"].get("prior_incomplete_protocol_id")
            == PRIOR_INCOMPLETE_PROTOCOL_ID
            and protocol["design"].get("prior_incomplete_results_may_be_pooled") is False
        ),
        "immutable_model_revision": (
            revision_evidence is not None
            and _validate_model_revision_evidence(revision_evidence)
            and protocol["provider"]["model_revision"] == revision_evidence["revision"]
            and protocol["provider"]["model_revision_evidence_sha256"]
            == _semantic_hash(revision_evidence)
        ),
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return {"protocol_id": PROTOCOL_ID, "checks": checks, "passed": not blockers, "blockers": blockers}


def write_repeated_freeze_v3(output: Path, payload: dict[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "formal_protocol.json", payload["protocol"])
    _write_json(output / "formal_schedule.json", payload["schedule"])
    _write_json(output / "formal_prepared_inputs.json", payload["prepared"])
    if payload["model_revision_evidence"] is not None:
        _write_json(output / "model_revision_evidence.json", payload["model_revision_evidence"])
    _write_json(output / "freeze_audit.json", verify_repeated_freeze_v3(output))


def _build_v3_schedule() -> ResearchLLMPilotSchedule:
    payload = build_research_llm_repeated_schedule(
        schedule_seed=SCHEDULE_SEED,
        replicates=REPLICATES,
    ).model_dump(mode="json")
    payload["protocol_id"] = PROTOCOL_ID
    for item in payload["items"]:
        item["run_id"] = item["run_id"].replace("formal-v2-", "formal-v3-", 1)
    return ResearchLLMPilotSchedule.model_validate(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze or verify the v3 repeated planning protocol.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
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
        report = verify_repeated_freeze_v3(args.verify)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["passed"] else 1
    write_repeated_freeze_v3(
        args.output,
        build_repeated_freeze_v3(
            manifest_path=args.manifest,
            implementation_commit=_git_head(),
            model_revision_evidence_path=args.model_revision_evidence,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
