from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark_platform.crosswalk import validate_crosswalk
from benchmark_platform.design_loader import load_frozen_design_bundle


AUDIT_ID = "fusionagent.benchmark-platform-core.p2-audit.v1"
CHECKPOINT_ID = "fusionagent.benchmark-platform-core.p2-checkpoint.v1"
IMPLEMENTATION_ROOT = "docs/current/benchmark/platform/v1/implementation"
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


def audit_p2(repo_root: Path, checkpoint_path: Path, *, probe: bool = True) -> dict[str, Any]:
    checkpoint = load(checkpoint_path)
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, details: Any) -> None:
        checks.append({"check_id": check_id, "required": True, "passed": bool(passed), "details": details})

    identity = {key: checkpoint.get(key) for key in ("checkpoint_id", "protocol_id", "stage", "gate", "status")}
    check("p2_checkpoint_identity", identity == {
        "checkpoint_id": CHECKPOINT_ID,
        "protocol_id": "fusionagent.benchmark-platform-implementation-protocol.v1",
        "stage": "P2",
        "gate": "BP2",
        "status": "stage_validated_offline",
    }, identity)

    design_root = repo_root / "docs/current/benchmark/v1"
    try:
        bundle = load_frozen_design_bundle(str(design_root), repo_root=str(repo_root))
        fixture = load(repo_root / "tests/fixtures/benchmark_platform/template_contract_valid.json")
        fixture["task_state"]["tasks"][0]["contract_ids"] = ["contract.road.fused.v1"]
        fixture["crosswalk"]["references"][0]["reference_id"] = "contract.road.fused.v1"
        report = validate_crosswalk(bundle, fixture)
        design_ok = len(bundle.matrix["cells"]) == 17 and report.reference_count == 1
        design_details = {"cell_count": len(bundle.matrix["cells"]), "reference_count": report.reference_count}
    except Exception as error:  # audit must turn any loader failure into a failed check
        design_ok = False
        design_details = {"error": f"{type(error).__name__}: {error}"}
    check("frozen_design_and_crosswalk", design_ok, design_details)

    hashes = checkpoint.get("files", [])
    errors: list[str] = []
    for item in hashes:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            errors.append("malformed checkpoint file entry")
            continue
        path = repo_root / item["path"]
        if not path.is_file() or file_hash(path) != item.get("sha256"):
            errors.append(item["path"])
    check("p2_artifact_hashes", not errors and bool(hashes), {"errors": errors, "count": len(hashes)})

    forbidden = ["schemas/benchmark.py", "kg/ontology/v1.0.0", "docs/current/benchmark/v1/"]
    changed = set(checkpoint.get("changed_paths", []))
    forbidden_hits = sorted(path for path in changed if any(path == prefix or path.startswith(prefix) for prefix in forbidden))
    check("p2_change_boundary", not forbidden_hits, {"forbidden_hits": forbidden_hits, "changed_paths": sorted(changed)})

    accounting = checkpoint.get("accounting", {})
    output_root = Path(str(checkpoint.get("paths", {}).get("future_output_root", "")))
    check("zero_instance_and_external_calls", accounting == ACCOUNTING and output_root.is_absolute() and not output_root.exists(), {"accounting": accounting, "output_root": str(output_root), "exists": output_root.exists()})
    check("next_gate_boundary", checkpoint.get("next_stage") == {"stage": "P3", "gate": "BP3", "automatic_progression": False}, checkpoint.get("next_stage"))

    failures = [item["check_id"] for item in checks if item["required"] and not item["passed"]]
    return {
        "audit_id": AUDIT_ID,
        "checkpoint_id": CHECKPOINT_ID,
        "protocol_id": "fusionagent.benchmark-platform-implementation-protocol.v1",
        "stage": "P2",
        "gate": "BP2",
        "checks": checks,
        "required_check_count": len(checks),
        "passed_required_check_count": len(checks) - len(failures),
        "required_failures": failures,
        "overall_passed": not failures,
        "stage_status": "complete" if not failures else "blocked_at_p2",
        "accounting": ACCOUNTING,
        "next_stage": "P3/BP3" if not failures else None,
        "automatic_progression": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the bounded benchmark platform P2 stage.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    checkpoint = args.checkpoint if args.checkpoint.is_absolute() else root / args.checkpoint
    output = args.output if args.output.is_absolute() else root / args.output
    result = audit_p2(root, checkpoint)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"overall_passed": result["overall_passed"], "required_failures": result["required_failures"]}))
    return 0 if result["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
