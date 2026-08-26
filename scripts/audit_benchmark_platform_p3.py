from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark_platform.design_loader import load_frozen_design_bundle
from benchmark_platform.generator import GenerationRequest, generate_development


AUDIT_ID = "fusionagent.benchmark-platform-core.p3-audit.v1"
CHECKPOINT_ID = "fusionagent.benchmark-platform-core.p3-checkpoint.v1"
ACCOUNTING = {
    "benchmark_instances_generated": 0,
    "provider_calls": 0,
    "judge_calls": 0,
    "formal_result_roots_created": 0,
    "confirmation_unsealed": False,
    "selective_e2e_selected": False,
    "platform_implementation_started": True,
}


def file_hash(path: Path) -> str:
    data = path.read_bytes().replace(bytes([13, 10]), bytes([10]))
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def audit_p3(repo_root: Path, checkpoint_path: Path) -> dict[str, Any]:
    checkpoint = load(checkpoint_path)
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, details: Any) -> None:
        checks.append({"check_id": check_id, "required": True, "passed": bool(passed), "details": details})

    identity = {key: checkpoint.get(key) for key in ("checkpoint_id", "protocol_id", "stage", "gate", "status")}
    check("p3_checkpoint_identity", identity == {
        "checkpoint_id": CHECKPOINT_ID,
        "protocol_id": "fusionagent.benchmark-platform-implementation-protocol.v1",
        "stage": "P3",
        "gate": "BP3",
        "status": "stage_validated_offline",
    }, identity)

    try:
        bundle = load_frozen_design_bundle(str(repo_root / "docs/current/benchmark/v1"), repo_root=str(repo_root))
        fixture = load(repo_root / "tests/fixtures/benchmark_platform/template_contract_valid.json")
        fixture["template_family_id"] = "TF-CONTRACT-REQUIREDNESS"
        fixture["capability_cell_ids"] = ["BC-CAUSAL-01"]
        fixture["task_state"]["tasks"][0]["contract_ids"] = ["contract.road.fused.v1"]
        fixture["crosswalk"]["references"][0]["reference_id"] = "contract.road.fused.v1"
        fixture["generation"]["seed_namespace"] = "fusionagent-benchmark-v1-development"
        fixture["generation"]["instance_id_pattern"] = "^BDV1-DEV-BC-[A-Z0-9-]+-[0-9]{3}$"
        request = GenerationRequest(partition="development", capability_cell_id="BC-CAUSAL-01", unit_index=0, seed_namespace="fusionagent-benchmark-v1-development", master_seed=2026081901)
        first = generate_development(bundle, fixture, request)
        second = generate_development(bundle, fixture, request)
        generation_pass = first.model_dump(mode="json") == second.model_dump(mode="json") and first.units[0].instance_id == "BDV1-DEV-BC-CAUSAL-01-000"
        generation_details = {"instance_id": first.units[0].instance_id, "instance_sha256": first.units[0].instance_sha256, "deterministic": generation_pass}
    except Exception as error:
        generation_pass = False
        generation_details = {"error": f"{type(error).__name__}: {error}"}
    check("deterministic_development_generation", generation_pass, generation_details)

    errors: list[str] = []
    for item in checkpoint.get("files", []):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            errors.append("malformed checkpoint file entry")
            continue
        path = repo_root / item["path"]
        if not path.is_file() or file_hash(path) != item.get("sha256"):
            errors.append(item["path"])
    check("p3_artifact_hashes", not errors and bool(checkpoint.get("files")), {"errors": errors, "count": len(checkpoint.get("files", []))})

    check("zero_external_calls_and_no_persisted_instances", checkpoint.get("accounting") == ACCOUNTING and not Path(checkpoint["paths"]["future_output_root"]).exists(), {"accounting": checkpoint.get("accounting"), "future_output_root": checkpoint["paths"]["future_output_root"]})
    check("next_gate_boundary", checkpoint.get("next_stage") == {"stage": "P4", "gate": "BP4", "automatic_progression": False}, checkpoint.get("next_stage"))

    failures = [item["check_id"] for item in checks if item["required"] and not item["passed"]]
    return {
        "audit_id": AUDIT_ID,
        "checkpoint_id": CHECKPOINT_ID,
        "protocol_id": "fusionagent.benchmark-platform-implementation-protocol.v1",
        "stage": "P3",
        "gate": "BP3",
        "checks": checks,
        "required_check_count": len(checks),
        "passed_required_check_count": len(checks) - len(failures),
        "required_failures": failures,
        "overall_passed": not failures,
        "stage_status": "complete" if not failures else "blocked_at_p3",
        "accounting": ACCOUNTING,
        "next_stage": "P4/BP4" if not failures else None,
        "automatic_progression": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the bounded benchmark platform P3 stage.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    checkpoint = args.checkpoint if args.checkpoint.is_absolute() else root / args.checkpoint
    output = args.output if args.output.is_absolute() else root / args.output
    result = audit_p3(root, checkpoint)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"overall_passed": result["overall_passed"], "required_failures": result["required_failures"]}))
    return 0 if result["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
