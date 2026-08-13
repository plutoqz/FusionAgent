from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.inmemory_repository import InMemoryKGRepository
from schemas.research_case_manifest import load_research_case_manifest
from schemas.research_llm_pilot import ResearchPlanningDecision, build_research_llm_formal_schedule
from scripts.run_research_llm_pilot import (
    SYSTEM_PROMPT,
    _conservative_token_estimate,
    prepare_research_schedule,
)
from services.research_plan_evaluation import EVALUATOR_ID


PROTOCOL_ID = "fusionagent.planning-formal.v1"
SCHEDULE_SEED = 20260813
IMPLEMENTATION_PATHS = (
    "llm/providers/openai_compatible.py",
    "schemas/research_case_manifest.py",
    "schemas/research_llm_pilot.py",
    "scripts/run_research_llm_pilot.py",
    "services/research_baselines.py",
    "services/research_plan_evaluation.py",
)


def build_formal_freeze(
    *,
    manifest_path: Path,
    implementation_commit: str,
    model_revision_evidence_path: Path | None = None,
) -> dict[str, Any]:
    manifest = load_research_case_manifest(manifest_path)
    schedule = build_research_llm_formal_schedule(schedule_seed=SCHEDULE_SEED)
    prepared = prepare_research_schedule(manifest, schedule)
    max_output_tokens = 16384
    token_budget = 600000
    conservative_bound = sum(
        _conservative_token_estimate(SYSTEM_PROMPT, item["payload"]) + max_output_tokens
        for item in prepared
    )
    model_revision_evidence = _load_model_revision_evidence(model_revision_evidence_path)
    blockers = []
    if conservative_bound > token_budget:
        blockers.append("formal_token_budget_below_conservative_bound")
    if model_revision_evidence is None:
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
                if model_revision_evidence is not None
                else "provider_reported_exact_id"
            ),
            "immutable_model_revision_evidenced": model_revision_evidence is not None,
            "model_revision": (
                model_revision_evidence["revision"] if model_revision_evidence is not None else None
            ),
            "model_revision_evidence_sha256": (
                _semantic_hash(model_revision_evidence)
                if model_revision_evidence is not None
                else None
            ),
            "api_key_storage": "environment_only",
            "model_registry_probe": {
                "observed_on": "2026-08-13",
                "endpoint": "/models",
                "id": "deepseek-v4-flash",
                "object": "model",
                "owned_by": "deepseek",
                "created": None,
                "immutable_revision_field_present": False,
            },
        },
        "generation": {
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "max_output_tokens": max_output_tokens,
            "transport_retries": 0,
            "semantic_repairs": 0,
            "json_salvage": "forbidden",
            "fallback": "forbidden",
        },
        "design": {
            "cases": list(schedule.cases),
            "llm_conditions": list(schedule.knowledge_conditions),
            "llm_repetitions": 1,
            "llm_call_count": len(schedule.items),
            "deterministic_groups": ["fixed_workflow", "rules_only", "kg_only"],
            "schedule_seed": SCHEDULE_SEED,
            "stability_claim_eligible": False,
            "negative_control_case_ids": list(manifest.negative_control_case_ids),
        },
        "budget": {
            "batch_token_budget": token_budget,
            "conservative_batch_bound": conservative_bound,
            "bound_within_budget": conservative_bound <= token_budget,
        },
        "identities": {
            "kg": InMemoryKGRepository(experience_policy="pinned_snapshot").get_knowledge_identity(),
            "manifest_sha256": _file_hash(manifest_path),
            "output_schema_sha256": _semantic_hash(ResearchPlanningDecision.model_json_schema()),
            "system_prompt_sha256": _semantic_hash(SYSTEM_PROMPT),
            "evaluator_id": EVALUATOR_ID,
            "evaluator_source_sha256": _file_hash(REPO_ROOT / "services/research_plan_evaluation.py"),
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
        },
    }
    return {
        "protocol": protocol,
        "schedule": schedule.model_dump(mode="json"),
        "prepared": prepared,
        "model_revision_evidence": model_revision_evidence,
    }


def verify_formal_freeze(root: Path) -> dict[str, Any]:
    protocol = _read_json(root / "formal_protocol.json")
    schedule = _read_json(root / "formal_schedule.json")
    prepared = _read_json(root / "formal_prepared_inputs.json")
    evidence_path = root / "model_revision_evidence.json"
    model_revision_evidence = _read_json(evidence_path) if evidence_path.exists() else None
    checks = {
        "protocol_id": protocol.get("protocol_id") == PROTOCOL_ID,
        "schedule_hash": protocol["identities"]["schedule_sha256"] == _semantic_hash(schedule),
        "prepared_inputs_hash": protocol["identities"]["prepared_inputs_sha256"] == _semantic_hash(prepared),
        "manifest_hash": protocol["identities"]["manifest_sha256"]
        == _file_hash(REPO_ROOT / "docs/current/research-case-manifest-v1.json"),
        "output_schema_hash": protocol["identities"]["output_schema_sha256"]
        == _semantic_hash(ResearchPlanningDecision.model_json_schema()),
        "evaluator_hash": protocol["identities"]["evaluator_source_sha256"]
        == _file_hash(REPO_ROOT / "services/research_plan_evaluation.py"),
        "implementation_hashes": all(
            expected == _file_hash(REPO_ROOT / path)
            for path, expected in protocol["identities"]["implementation_files"].items()
        ),
        "call_count": len(schedule["items"]) == len(prepared) == 18,
        "budget_bound": protocol["budget"]["bound_within_budget"] is True,
        "immutable_model_revision": (
            model_revision_evidence is not None
            and _validate_model_revision_evidence(model_revision_evidence)
            and protocol["provider"]["immutable_model_revision_evidenced"] is True
            and protocol["provider"]["model_revision"] == model_revision_evidence["revision"]
            and protocol["provider"]["model_revision_evidence_sha256"]
            == _semantic_hash(model_revision_evidence)
        ),
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return {
        "protocol_id": PROTOCOL_ID,
        "checks": checks,
        "passed": not blockers,
        "blockers": blockers,
    }


def write_formal_freeze(output: Path, payload: dict[str, Any]) -> None:
    output.mkdir(parents=True, exist_ok=False)
    _write_json(output / "formal_protocol.json", payload["protocol"])
    _write_json(output / "formal_schedule.json", payload["schedule"])
    _write_json(output / "formal_prepared_inputs.json", payload["prepared"])
    if payload["model_revision_evidence"] is not None:
        _write_json(output / "model_revision_evidence.json", payload["model_revision_evidence"])
    _write_json(output / "freeze_audit.json", verify_formal_freeze(output))


def _load_model_revision_evidence(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    evidence = _read_json(path)
    if not _validate_model_revision_evidence(evidence):
        raise ValueError("Model revision evidence is incomplete or does not match the frozen provider/model.")
    return evidence


def _validate_model_revision_evidence(evidence: Any) -> bool:
    if not isinstance(evidence, dict):
        return False
    required_strings = ("revision", "evidence_source", "issued_at")
    return (
        evidence.get("provider") == "deepseek_official"
        and evidence.get("model") == "deepseek-v4-flash"
        and evidence.get("immutable") is True
        and evidence.get("production_release") is True
        and all(isinstance(evidence.get(key), str) and evidence[key].strip() for key in required_strings)
    )


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _semantic_hash(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze or verify the planning-only formal protocol.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify", type=Path)
    parser.add_argument(
        "--model-revision-evidence",
        type=Path,
        help="Provider-issued JSON evidence for an immutable production model revision.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "docs/current/research-case-manifest-v1.json",
    )
    args = parser.parse_args()
    if bool(args.output) == bool(args.verify):
        raise ValueError("Specify exactly one of --output or --verify")
    if args.verify:
        report = verify_formal_freeze(args.verify)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["passed"] else 1
    write_formal_freeze(
        args.output,
        build_formal_freeze(
            manifest_path=args.manifest,
            implementation_commit=_git_head(),
            model_revision_evidence_path=args.model_revision_evidence,
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
