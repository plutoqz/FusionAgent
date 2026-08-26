from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark_platform.canonical import canonical_sha256
from benchmark_platform.generator import GeneratedMember, GeneratedUnit
from benchmark_platform.relations import validate_relations
from benchmark_platform.views import project_views


AUDIT_ID = "fusionagent.benchmark-platform-core.p4-audit.v1"
CHECKPOINT_ID = "fusionagent.benchmark-platform-core.p4-checkpoint.v1"
ACCOUNTING = {"benchmark_instances_generated": 0, "provider_calls": 0, "judge_calls": 0, "formal_result_roots_created": 0, "confirmation_unsealed": False, "selective_e2e_selected": False, "platform_implementation_started": True}


def file_hash(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes().replace(bytes([13, 10]), bytes([10]))).hexdigest()}"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def audit_p4(repo_root: Path, checkpoint_path: Path) -> dict[str, Any]:
    checkpoint = load(checkpoint_path)
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, details: Any) -> None:
        checks.append({"check_id": check_id, "required": True, "passed": bool(passed), "details": details})

    identity = {key: checkpoint.get(key) for key in ("checkpoint_id", "protocol_id", "stage", "gate", "status")}
    check("p4_checkpoint_identity", identity == {"checkpoint_id": CHECKPOINT_ID, "protocol_id": "fusionagent.benchmark-platform-implementation-protocol.v1", "stage": "P4", "gate": "BP4", "status": "stage_validated_offline"}, identity)
    try:
        fixture = load(repo_root / "tests/fixtures/benchmark_platform/template_contract_valid.json")
        payload = json.loads(json.dumps(fixture))
        member = GeneratedMember(member_index=0, member_payload=payload, member_sha256=canonical_sha256(payload))
        unit = GeneratedUnit(instance_id="BDV1-DEV-BC-DIAG-03-000", template_family_id="TF-PLAN-STRUCTURE-INVALID", capability_cell_id="BC-DIAG-03", partition="development", unit_index=0, unit_type="single", seed=1, template_sha256="sha256:" + "1" * 64, members=(member,), instance_sha256="sha256:" + "2" * 64)
        relation = validate_relations(unit, fixture, "planning.structure_invalid", {"planning.structure_invalid"})
        views = project_views(fixture, fixture["views"])
        behavior_pass = relation.passed and views.leakage_audit.passed and "oracle" not in views.planner.payload
        behavior_details = {"relation_passed": relation.passed, "leakage_passed": views.leakage_audit.passed, "planner_keys": sorted(views.planner.payload)}
    except Exception as error:
        behavior_pass = False
        behavior_details = {"error": f"{type(error).__name__}: {error}"}
    check("relations_and_allowlist_views", behavior_pass, behavior_details)

    forbidden_imports = {"requests", "httpx", "urllib", "socket", "openai", "anthropic", "neo4j", "llm"}
    import_hits: list[str] = []
    for relative in ("benchmark_platform/relations.py", "benchmark_platform/views.py"):
        tree = ast.parse((repo_root / relative).read_text(encoding="utf-8"), filename=relative)
        for node in ast.walk(tree):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            for name in names:
                if name.split(".", 1)[0] in forbidden_imports:
                    import_hits.append(f"{relative}:{name}")
    check("offline_import_boundary", not import_hits, {"forbidden_imports": import_hits})

    errors: list[str] = []
    for item in checkpoint.get("files", []):
        path = repo_root / str(item.get("path", ""))
        if not path.is_file() or file_hash(path) != item.get("sha256"):
            errors.append(str(item.get("path")))
    check("p4_artifact_hashes", not errors and bool(checkpoint.get("files")), {"errors": errors, "count": len(checkpoint.get("files", []))})
    check("zero_call_and_no_output_root", checkpoint.get("accounting") == ACCOUNTING and not Path(checkpoint["paths"]["future_output_root"]).exists(), {"accounting": checkpoint.get("accounting"), "future_output_root": checkpoint["paths"]["future_output_root"]})
    check("next_gate_boundary", checkpoint.get("next_stage") == {"stage": "P5", "gate": "BP5", "automatic_progression": False}, checkpoint.get("next_stage"))
    failures = [item["check_id"] for item in checks if item["required"] and not item["passed"]]
    return {"audit_id": AUDIT_ID, "checkpoint_id": CHECKPOINT_ID, "protocol_id": "fusionagent.benchmark-platform-implementation-protocol.v1", "stage": "P4", "gate": "BP4", "checks": checks, "required_check_count": len(checks), "passed_required_check_count": len(checks) - len(failures), "required_failures": failures, "overall_passed": not failures, "stage_status": "complete" if not failures else "blocked_at_p4", "accounting": ACCOUNTING, "next_stage": "P5/BP5" if not failures else None, "automatic_progression": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the bounded benchmark platform P4 stage.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    checkpoint = args.checkpoint if args.checkpoint.is_absolute() else root / args.checkpoint
    output = args.output if args.output.is_absolute() else root / args.output
    result = audit_p4(root, checkpoint)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"overall_passed": result["overall_passed"], "required_failures": result["required_failures"]}))
    return 0 if result["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
