from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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
from services.research_manifest_validation import validate_manifest_crosswalk
from services.research_plan_evaluation import EVALUATOR_ID


PROTOCOL_ID = "fusionagent.method-b-independent-confirmation.v1"
METHOD_B_CONDITION = "task_conditioned_contract_aware_kg"
EXPECTED_CONDITIONS = {
    METHOD_B_CONDITION,
    "llm_only",
    "llm_full_contract_kg",
}
DEFAULT_MANIFEST = REPO_ROOT / "docs/current/research-case-manifest-confirmation-v1.json"
DEFAULT_REGISTRATION = REPO_ROOT / "docs/current/research-protocol-method-confirmation-v1.json"


def prepare_confirmation_inputs(
    manifest_path: Path,
    registration_path: Path = DEFAULT_REGISTRATION,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    registration = _read_json(registration_path)
    _validate_registration(registration, manifest_path)
    manifest = load_research_case_manifest(manifest_path)
    repository = InMemoryKGRepository(experience_policy="pinned_snapshot")
    failures = validate_manifest_crosswalk(manifest, repository)
    if failures:
        raise RuntimeError(f"Confirmation manifest KG crosswalk is not closed: {failures}")

    conditions = registration["design"]["conditions"]
    repetitions = registration["design"]["repetitions"]
    cases = {case.case_id: case for case in manifest.cases}
    items = [
        {
            "run_id": f"confirmation-{case_id.lower()}-{condition}-r{replicate}",
            "case_id": case_id,
            "knowledge_condition": condition,
            "replicate": replicate,
            "input_variant": PROTOCOL_ID,
        }
        for case_id in sorted(cases)
        for condition in conditions
        for replicate in range(1, repetitions + 1)
    ]
    random.Random(registration["design"]["schedule_seed"]).shuffle(items)

    factory = CanonicalContextFactory(repository)
    prepared: list[dict[str, Any]] = []
    for item in items:
        case = cases[item["case_id"]]
        if item["knowledge_condition"] == METHOD_B_CONDITION:
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
        "schedule_seed": registration["design"]["schedule_seed"],
        "cases": sorted(cases),
        "knowledge_conditions": conditions,
        "replicates": repetitions,
        "items": items,
        "metadata": {
            "fallback": "forbidden",
            "transport_retries": 0,
            "semantic_repairs": 0,
            "historical_result_reuse": "forbidden",
            "excluded_case_ids": registration["design"][
                "development_and_prior_validation_cases_excluded"
            ],
        },
    }
    return registration, schedule, prepared


def build_freeze(
    *,
    manifest_path: Path,
    registration_path: Path,
    implementation_commit: str,
    model_revision_evidence_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    registration, schedule, prepared = prepare_confirmation_inputs(
        manifest_path,
        registration_path,
    )
    evidence = _read_json(model_revision_evidence_path)
    _validate_model_revision_evidence(registration, evidence, model_revision_evidence_path)
    generation = registration["generation"]
    conservative_bound = sum(
        _conservative_token_estimate(SYSTEM_PROMPT, item["payload"])
        + generation["max_output_tokens"]
        for item in prepared
    )
    if conservative_bound > generation["batch_token_budget"]:
        raise RuntimeError(
            "Confirmation conservative token bound exceeds budget: "
            f"{conservative_bound} > {generation['batch_token_budget']}"
        )

    protocol = copy.deepcopy(registration)
    protocol["formal_ready"] = True
    protocol["implementation_commit"] = implementation_commit
    protocol["budget"] = {
        "batch_token_budget": generation["batch_token_budget"],
        "conservative_batch_bound": conservative_bound,
        "bound_within_budget": True,
        "paid_call_count": len(prepared),
    }
    protocol["identities"].update(
        {
            "registration_file_sha256": _file_hash(registration_path),
            "model_revision_evidence_semantic_sha256": semantic_hash(evidence),
            "schedule_sha256": semantic_hash(schedule),
            "prepared_inputs_sha256": semantic_hash(prepared),
        }
    )
    return protocol, schedule, prepared


def verify_freeze(
    root: Path,
    *,
    manifest_path: Path,
    registration_path: Path,
) -> dict[str, Any]:
    protocol = _read_json(root / "formal_protocol.json")
    schedule = _read_json(root / "schedule.json")
    prepared = _read_json(root / "prepared_inputs.json")
    registration = _read_json(registration_path)
    repository = InMemoryKGRepository(experience_policy="pinned_snapshot")
    manifest = load_research_case_manifest(manifest_path)
    checks = {
        "protocol_id": protocol.get("protocol_id") == PROTOCOL_ID,
        "protocol_frozen": protocol.get("protocol_status") == "frozen"
        and protocol.get("formal_ready") is True,
        "registration_unchanged": protocol["identities"]["registration_file_sha256"]
        == _file_hash(registration_path),
        "manifest_frozen": manifest.status == "frozen",
        "manifest_unchanged": registration["identities"]["manifest_file_sha256"]
        == _file_hash(manifest_path),
        "crosswalk_closed": validate_manifest_crosswalk(manifest, repository) == [],
        "call_grid": len(schedule.get("items", [])) == 27 and len(prepared) == 27,
        "case_grid": set(schedule.get("cases", [])) == {"H07", "H08", "H09"},
        "condition_grid": set(schedule.get("knowledge_conditions", []))
        == EXPECTED_CONDITIONS,
        "replicate_grid": {item["replicate"] for item in schedule.get("items", [])}
        == {1, 2, 3},
        "unique_run_ids": len({item["run_id"] for item in schedule.get("items", [])})
        == 27,
        "historical_cases_excluded": not {
            item["case_id"] for item in schedule.get("items", [])
        }.intersection(registration["design"]["development_and_prior_validation_cases_excluded"]),
        "historical_result_reuse_forbidden": schedule["metadata"]["historical_result_reuse"]
        == "forbidden",
        "schedule_hash": protocol["identities"]["schedule_sha256"]
        == semantic_hash(schedule),
        "prepared_inputs_hash": protocol["identities"]["prepared_inputs_sha256"]
        == semantic_hash(prepared),
        "prompt_hash": registration["identities"]["system_prompt_sha256"]
        == semantic_hash(SYSTEM_PROMPT),
        "schema_hash": registration["identities"]["output_schema_sha256"]
        == semantic_hash(ResearchPlanningDecision.model_json_schema()),
        "evaluator_id": registration["identities"]["evaluator_id"] == EVALUATOR_ID,
        "evaluator_hash": registration["identities"]["evaluator_source_sha256"]
        == _file_hash(REPO_ROOT / "services/research_plan_evaluation.py"),
        "method_id": protocol.get("method_id") == METHOD_B_ID,
        "method_hash": registration["identities"]["method_source_sha256"]
        == _file_hash(REPO_ROOT / "services/research_contract_aware_planning.py"),
        "kg_identity": registration["identities"]["kg_identity"]
        == repository.get_knowledge_identity(),
        "generation_locked": protocol["generation"] == registration["generation"],
        "zero_retry_repair_fallback": protocol["generation"]["transport_retries"] == 0
        and protocol["generation"]["semantic_repairs"] == 0
        and protocol["generation"]["json_salvage"] == "forbidden"
        and protocol["generation"]["fallback"] == "forbidden",
        "budget_bound": protocol["budget"]["bound_within_budget"] is True,
        "gold_not_exposed": all(
            not (FORBIDDEN_PLANNER_KEYS & set(_nested_keys(item["payload"])))
            for item in prepared
        ),
    }
    return {"protocol_id": PROTOCOL_ID, "checks": checks, "passed": all(checks.values())}


def run_confirmation(
    root: Path,
    *,
    manifest_path: Path,
    registration_path: Path,
    model_revision_evidence_path: Path,
    execute: bool,
    authorization_token: str | None,
) -> int:
    if root.exists():
        raise RuntimeError(f"Refusing to overwrite confirmation evidence root: {root}")
    _require_clean_worktree()
    registration = _read_json(registration_path)
    _require_method_freeze_ancestor(registration["identities"]["method_freeze_commit"])
    if execute:
        if authorization_token != PROTOCOL_ID:
            raise RuntimeError(
                f"Real execution requires --authorization-token {PROTOCOL_ID}"
            )
        _validate_execution_environment(registration)

    root.mkdir(parents=True)
    protocol, schedule, prepared = build_freeze(
        manifest_path=manifest_path,
        registration_path=registration_path,
        implementation_commit=_git_head(),
        model_revision_evidence_path=model_revision_evidence_path,
    )
    shutil.copy2(registration_path, root / "protocol_registration.json")
    shutil.copy2(model_revision_evidence_path, root / "model_revision_evidence.json")
    _write_json(root / "formal_protocol.json", protocol)
    _write_json(root / "schedule.json", schedule)
    _write_json(root / "prepared_inputs.json", prepared)
    audit = verify_freeze(
        root,
        manifest_path=manifest_path,
        registration_path=registration_path,
    )
    _write_json(root / "freeze_audit.json", audit)
    if not audit["passed"]:
        raise RuntimeError("Confirmation freeze audit failed; no provider calls were made.")
    if not execute:
        _write_json(
            root / "preflight.json",
            {
                "status": "formal_ready",
                "paid_provider_calls_made": 0,
                "execution_authorized": False,
            },
        )
        return 0

    results = execute_pilot(
        prepared,
        root,
        pilot_scope="method_b_independent_confirmation",
        claim_eligible=False,
        protocol_id=PROTOCOL_ID,
        model_revision=protocol["provider"]["model_revision"],
    )
    _write_json(
        root / "formal_summary.json",
        {
            "status": "completed"
            if len(results) == len(prepared)
            else "stopped_with_retained_failures",
            "scheduled_calls": len(prepared),
            "executed_calls": len(results),
            "successful_calls": sum(item.get("success") is True for item in results),
            "failed_calls": sum(item.get("success") is not True for item in results),
            "manual_review_status": "pending",
            "comparative_claim_status": "ineligible_pending_frozen_analysis_and_blind_review",
            "historical_results_reused": 0,
        },
    )
    return 0


def _validate_registration(registration: dict[str, Any], manifest_path: Path) -> None:
    if registration.get("protocol_id") != PROTOCOL_ID:
        raise RuntimeError("Unexpected confirmation protocol registration.")
    if registration.get("protocol_status") != "frozen":
        raise RuntimeError("Confirmation protocol registration is not frozen.")
    manifest = load_research_case_manifest(manifest_path)
    if manifest.status != "frozen":
        raise RuntimeError("Confirmation manifest must be frozen.")
    case_ids = sorted(case.case_id for case in manifest.cases)
    if case_ids != sorted(registration["design"]["case_ids"]):
        raise RuntimeError("Confirmation manifest cases differ from the frozen protocol.")
    if registration["design"]["call_count"] != 27:
        raise RuntimeError("Confirmation protocol must remain a 27-call design.")
    if set(registration["design"]["conditions"]) != EXPECTED_CONDITIONS:
        raise RuntimeError("Confirmation conditions differ from B, LLM-only, and Full KG.")
    if registration["design"]["repetitions"] != 3:
        raise RuntimeError("Confirmation protocol must retain three repetitions.")
    if registration["identities"]["manifest_file_sha256"] != _file_hash(manifest_path):
        raise RuntimeError("Confirmation manifest hash differs from the frozen protocol.")


def _validate_model_revision_evidence(
    registration: dict[str, Any],
    evidence: dict[str, Any],
    evidence_path: Path,
) -> None:
    provider = registration["provider"]
    if _file_hash(evidence_path) != provider["model_revision_evidence_file_sha256"]:
        raise RuntimeError("Model revision evidence file differs from the frozen protocol.")
    required = {
        "provider": provider["provider"],
        "model": provider["model"],
        "revision": provider["model_revision"],
        "immutable": True,
        "production_release": True,
    }
    mismatches = {
        key: {"expected": value, "observed": evidence.get(key)}
        for key, value in required.items()
        if evidence.get(key) != value
    }
    if mismatches:
        raise RuntimeError(f"Model revision evidence mismatch: {mismatches}")


def _validate_execution_environment(registration: dict[str, Any]) -> None:
    provider = registration["provider"]
    generation = registration["generation"]
    expected = {
        "GEOFUSION_LLM_MODEL": provider["model"],
        "GEOFUSION_LLM_MAX_OUTPUT_TOKENS": str(generation["max_output_tokens"]),
        "GEOFUSION_LLM_PILOT_TOKEN_BUDGET": str(generation["batch_token_budget"]),
        "GEOFUSION_LLM_TIMEOUT_SEC": str(generation["request_timeout_seconds"]),
    }
    mismatches = {
        key: {"expected": value, "observed": os.getenv(key)}
        for key, value in expected.items()
        if os.getenv(key) != value
    }
    base_url = os.getenv("GEOFUSION_LLM_BASE_URL")
    if not base_url or urlsplit(base_url).netloc != provider["base_url_host"]:
        mismatches["GEOFUSION_LLM_BASE_URL"] = {
            "expected_host": provider["base_url_host"],
            "observed": base_url,
        }
    if not (os.getenv("OPENAI_API_KEY") or os.getenv("GEOFUSION_LLM_API_KEY")):
        mismatches["provider_credentials"] = {"expected": "present", "observed": "missing"}
    if mismatches:
        raise RuntimeError(f"Frozen execution environment mismatch: {mismatches}")


def _require_clean_worktree() -> None:
    status = subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=REPO_ROOT, text=True
    ).strip()
    if status:
        raise RuntimeError("Confirmation preflight requires a clean worktree.")


def _require_method_freeze_ancestor(commit: str) -> None:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"],
        cwd=REPO_ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Frozen method commit is not an ancestor of HEAD: {commit}")


def _git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
    ).strip()


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Freeze, preflight, or execute the independent 27-call confirmation protocol."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--registration", type=Path, default=DEFAULT_REGISTRATION)
    parser.add_argument("--model-revision-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--authorization-token")
    args = parser.parse_args()
    return run_confirmation(
        args.output,
        manifest_path=args.manifest,
        registration_path=args.registration,
        model_revision_evidence_path=args.model_revision_evidence,
        execute=args.execute,
        authorization_token=args.authorization_token,
    )


if __name__ == "__main__":
    raise SystemExit(main())
