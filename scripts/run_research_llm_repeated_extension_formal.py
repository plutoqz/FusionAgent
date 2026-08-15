from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.freeze_research_repeated_extension_protocol import (
    EXPECTED_CALL_COUNT,
    verify_extension_freeze,
)
from scripts.run_research_llm_pilot import _attempt_total_tokens, execute_pilot
from scripts.run_research_llm_repeated_formal import (
    _git_head,
    _read_json,
    _write_json,
    assert_frozen_source_state,
)


def validate_extension_execution(
    freeze_root: Path,
    base_evidence_root: Path,
    *,
    env: dict[str, str],
    require_api_key: bool = True,
) -> dict[str, Any]:
    audit = verify_extension_freeze(
        freeze_root,
        base_evidence_root=base_evidence_root,
    )
    if not audit["passed"]:
        raise RuntimeError(f"Repeated extension freeze audit failed: {audit['blockers']}")
    protocol = _read_json(freeze_root / "formal_protocol.json")
    if protocol.get("formal_ready") is not True or protocol.get("protocol_status") != "frozen":
        raise RuntimeError("Repeated extension protocol is not frozen and ready for execution.")
    expected = {
        "GEOFUSION_LLM_MODEL": protocol["provider"]["requested_model"],
        "GEOFUSION_LLM_MAX_OUTPUT_TOKENS": str(protocol["generation"]["max_output_tokens"]),
        "GEOFUSION_LLM_PILOT_TOKEN_BUDGET": str(protocol["budget"]["batch_token_budget"]),
        "GEOFUSION_LLM_TIMEOUT_SEC": str(protocol["generation"]["request_timeout_seconds"]),
    }
    mismatches = {
        name: {"expected": value, "actual": env.get(name)}
        for name, value in expected.items()
        if env.get(name) != value
    }
    actual_host = urlsplit(env.get("GEOFUSION_LLM_BASE_URL", "")).netloc
    expected_host = protocol["provider"]["base_url_host"]
    if actual_host != expected_host:
        mismatches["GEOFUSION_LLM_BASE_URL.host"] = {
            "expected": expected_host,
            "actual": actual_host or None,
        }
    if require_api_key and not (env.get("OPENAI_API_KEY") or env.get("GEOFUSION_LLM_API_KEY")):
        mismatches["api_key"] = {"expected": "configured", "actual": "missing"}
    if mismatches:
        raise RuntimeError(f"Repeated extension environment does not match the freeze: {mismatches}")
    return protocol


def run_extension_formal(
    freeze_root: Path,
    base_evidence_root: Path,
    output: Path,
    *,
    execute: bool,
) -> int:
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite repeated extension evidence directory: {output}")
    protocol = validate_extension_execution(
        freeze_root,
        base_evidence_root,
        env=dict(os.environ),
        require_api_key=execute,
    )
    assert_frozen_source_state(protocol)
    output.mkdir(parents=True)
    for source, target in (
        ("formal_protocol.json", "formal_protocol.json"),
        ("freeze_audit.json", "freeze_audit.json"),
        ("formal_schedule.json", "schedule.json"),
        ("formal_prepared_inputs.json", "prepared_inputs.json"),
        ("model_revision_evidence.json", "model_revision_evidence.json"),
        ("base_evidence_binding.json", "base_evidence_binding.json"),
    ):
        shutil.copy2(freeze_root / source, output / target)
    timeout_seconds = protocol["generation"]["request_timeout_seconds"]
    _write_json(
        output / "execution_identity.json",
        {
            "protocol_id": protocol["protocol_id"],
            "combined_protocol_id": protocol["combined_protocol_id"],
            "frozen_implementation_commit": protocol["implementation_commit"],
            "execution_commit": _git_head(),
            "execution_commit_descends_from_frozen_implementation": True,
            "worktree_clean_at_start": True,
            "execute_provider_calls": execute,
            "request_timeout_seconds": timeout_seconds,
            "base_protocol_id": protocol["base_evidence"]["base_protocol_id"],
            "base_audit_sha256": protocol["base_evidence"]["formal_automatic_audit_sha256"],
            "prior_incomplete_v2_pooled": False,
        },
    )
    if not execute:
        _write_json(
            output / "preflight.json",
            {
                "status": "formal_ready",
                "call_count": EXPECTED_CALL_COUNT,
                "extension_replicates": protocol["design"]["extension_replicates"],
                "target_repetitions": protocol["design"]["target_repetitions"],
                "protocol_id": protocol["protocol_id"],
                "implementation_commit": protocol["implementation_commit"],
                "model_revision": protocol["provider"]["model_revision"],
                "request_timeout_seconds": timeout_seconds,
                "base_evidence_binding_valid": True,
                "paid_provider_calls_made": 0,
                "api_key_configured": bool(
                    os.getenv("OPENAI_API_KEY") or os.getenv("GEOFUSION_LLM_API_KEY")
                ),
                "execution_ready": bool(
                    os.getenv("OPENAI_API_KEY") or os.getenv("GEOFUSION_LLM_API_KEY")
                ),
            },
        )
        return 0
    prepared = _read_json(output / "prepared_inputs.json")
    results = execute_pilot(
        prepared,
        output,
        pilot_scope="planning_only_repeated_formal_extension_repetitions_4_5",
        claim_eligible=False,
        protocol_id=protocol["protocol_id"],
        model_revision=protocol["provider"]["model_revision"],
    )
    execution_config = _read_json(output / "execution_config.json")
    execution_config.update(
        request_timeout_seconds=timeout_seconds,
        base_protocol_id=protocol["base_evidence"]["base_protocol_id"],
        base_audit_sha256=protocol["base_evidence"]["formal_automatic_audit_sha256"],
        prior_incomplete_v2_pooled=False,
    )
    _write_json(output / "execution_config.json", execution_config)
    _write_json(
        output / "formal_summary.json",
        {
            "status": (
                "completed"
                if len(results) == EXPECTED_CALL_COUNT and all(item["success"] for item in results)
                else "completed_with_observed_failures"
            ),
            "scheduled_calls": EXPECTED_CALL_COUNT,
            "executed_calls": len(results),
            "successful_calls": sum(item["success"] for item in results),
            "failed_calls": sum(not item["success"] for item in results),
            "consumed_tokens": sum(_attempt_total_tokens(item.get("attempt")) for item in results),
            "failed_calls_replaced": False,
            "extension_replicates": protocol["design"]["extension_replicates"],
            "target_repetitions": protocol["design"]["target_repetitions"],
            "base_protocol_id": protocol["base_evidence"]["base_protocol_id"],
            "base_audit_sha256": protocol["base_evidence"]["formal_automatic_audit_sha256"],
            "prior_incomplete_v2_pooled": False,
            "manual_review_status": "pending_combined_90_run_analysis",
            "comparative_claim_status": "pending_combined_analysis_and_manual_review",
        },
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute the frozen 36-call planning extension.")
    parser.add_argument("--freeze-root", type=Path, required=True)
    parser.add_argument("--base-evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="Make the 36 paid provider calls.")
    args = parser.parse_args()
    return run_extension_formal(
        args.freeze_root,
        args.base_evidence_root,
        args.output,
        execute=args.execute,
    )


if __name__ == "__main__":
    raise SystemExit(main())
