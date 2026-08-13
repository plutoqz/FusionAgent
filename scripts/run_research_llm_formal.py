from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.freeze_research_formal_protocol import verify_formal_freeze
from scripts.run_research_llm_pilot import _attempt_total_tokens, execute_pilot


def validate_formal_execution(freeze_root: Path, *, env: dict[str, str]) -> dict[str, Any]:
    audit = verify_formal_freeze(freeze_root)
    if not audit["passed"]:
        raise RuntimeError(f"Formal freeze audit failed: {audit['blockers']}")

    protocol = _read_json(freeze_root / "formal_protocol.json")
    if protocol.get("formal_ready") is not True or protocol.get("protocol_status") != "frozen":
        raise RuntimeError("Formal protocol is not frozen and ready for execution.")

    expected = {
        "GEOFUSION_LLM_MODEL": protocol["provider"]["requested_model"],
        "GEOFUSION_LLM_MAX_OUTPUT_TOKENS": str(protocol["generation"]["max_output_tokens"]),
        "GEOFUSION_LLM_PILOT_TOKEN_BUDGET": str(protocol["budget"]["batch_token_budget"]),
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
    if not (env.get("OPENAI_API_KEY") or env.get("GEOFUSION_LLM_API_KEY")):
        mismatches["api_key"] = {"expected": "configured", "actual": "missing"}
    if mismatches:
        raise RuntimeError(f"Formal execution environment does not match the freeze: {mismatches}")
    return protocol


def assert_frozen_source_state(protocol: dict[str, Any]) -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()
    if head != protocol["implementation_commit"]:
        raise RuntimeError(
            f"Current HEAD {head} does not match frozen implementation {protocol['implementation_commit']}."
        )
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=REPO_ROOT,
        text=True,
    )
    if status.strip():
        raise RuntimeError("Formal execution requires a clean worktree.")


def run_formal(freeze_root: Path, output: Path, *, execute: bool) -> int:
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite formal evidence directory: {output}")
    protocol = validate_formal_execution(freeze_root, env=dict(os.environ))
    assert_frozen_source_state(protocol)

    output.mkdir(parents=True)
    shutil.copy2(freeze_root / "formal_protocol.json", output / "formal_protocol.json")
    shutil.copy2(freeze_root / "freeze_audit.json", output / "freeze_audit.json")
    shutil.copy2(freeze_root / "formal_schedule.json", output / "schedule.json")
    shutil.copy2(freeze_root / "formal_prepared_inputs.json", output / "prepared_inputs.json")
    shutil.copy2(
        freeze_root / "model_revision_evidence.json",
        output / "model_revision_evidence.json",
    )
    if not execute:
        _write_json(
            output / "preflight.json",
            {
                "status": "formal_ready",
                "call_count": protocol["design"]["llm_call_count"],
                "protocol_id": protocol["protocol_id"],
                "implementation_commit": protocol["implementation_commit"],
                "model_revision": protocol["provider"]["model_revision"],
                "paid_provider_calls_made": 0,
            },
        )
        return 0

    prepared = _read_json(output / "prepared_inputs.json")
    results = execute_pilot(
        prepared,
        output,
        pilot_scope="planning_only_formal",
        claim_eligible=True,
        protocol_id=protocol["protocol_id"],
        model_revision=protocol["provider"]["model_revision"],
    )
    _write_json(
        output / "formal_summary.json",
        {
            "status": (
                "completed" if len(results) == 18 and all(item["success"] for item in results)
                else "completed_with_observed_failures"
            ),
            "scheduled_calls": 18,
            "executed_calls": len(results),
            "successful_calls": sum(item["success"] for item in results),
            "failed_calls": sum(not item["success"] for item in results),
            "consumed_tokens": sum(_attempt_total_tokens(item.get("attempt")) for item in results),
            "failed_calls_replaced": False,
            "manual_review_status": "pending",
        },
    )
    return 0


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute a verified planning-only formal protocol.")
    parser.add_argument("--freeze-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="Make the 18 paid provider calls.")
    args = parser.parse_args()
    return run_formal(args.freeze_root, args.output, execute=args.execute)


if __name__ == "__main__":
    raise SystemExit(main())
