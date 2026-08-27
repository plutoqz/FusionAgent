from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark_platform.canonical import canonical_sha256
from benchmark_platform.store import ArtifactStore, ResumeRequest, RunBinding, StoreError


AUDIT_ID = "fusionagent.benchmark-platform-core.p5-audit.v1"
CHECKPOINT_ID = "fusionagent.benchmark-platform-core.p5-checkpoint.v1"
ACCOUNTING = {"benchmark_instances_generated": 0, "provider_calls": 0, "judge_calls": 0, "formal_result_roots_created": 0, "confirmation_unsealed": False, "selective_e2e_selected": False, "platform_implementation_started": True}


def file_hash(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes().replace(bytes([13, 10]), bytes([10]))).hexdigest()}"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _binding() -> RunBinding:
    return RunBinding(run_id="BDV1-DEV-P5-AUDIT", design_id="fusionagent.benchmark-design.v1", design_sha256="sha256:" + "1" * 64, template_sha256="sha256:" + "2" * 64, seed_namespace="fusionagent-benchmark-v1-development", master_seed=2026081901, code_revision="p5-audit", input_hashes={"design": "sha256:" + "3" * 64})


def _storage_replay() -> dict[str, bool]:
    with tempfile.TemporaryDirectory(prefix="benchmark-platform-p5-") as directory:
        binding = _binding()
        store = ArtifactStore.create_new(Path(directory) / "run", binding)
        store.commit_stage("design_bound", input_hashes={"design": binding.design_sha256}, output_paths=["design_binding.json"])
        store.write_json_artifact("template_snapshots/audit.json", {"fixture": "audit"})
        store.commit_stage("templates_validated", input_hashes={"template": binding.template_sha256}, output_paths=["template_snapshots/audit.json"])
        instance = {"instance_id": "BDV1-DEV-BC-CAUSAL-01-000", "instance_sha256": canonical_sha256({"fixture": "audit"})}
        store.append_jsonl("generation_attempts.jsonl", {"attempt_index": 0, "status": "valid"})
        store.append_instance(instance)
        store.commit_stage("generated", input_hashes={"generator": "sha256:" + "4" * 64}, output_paths=["generation_attempts.jsonl", "instances.jsonl"])
        resumed = store.resume(ResumeRequest(run_root=str(store.root), expected_stage="generated", binding=binding)).stage == "generated"
        try:
            store.append_instance(instance)
            duplicate_rejected = False
        except StoreError:
            duplicate_rejected = True
        (store.root / "instances.jsonl").write_text("{\"tampered\":true}\n", encoding="utf-8")
        try:
            store.resume(ResumeRequest(run_root=str(store.root), expected_stage="generated", binding=binding))
            tamper_rejected = False
        except StoreError:
            tamper_rejected = True
        return {"resumed": resumed, "duplicate_rejected": duplicate_rejected, "tamper_rejected": tamper_rejected}


def audit_p5(repo_root: Path, checkpoint_path: Path) -> dict[str, Any]:
    checkpoint = load(checkpoint_path)
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, details: Any) -> None:
        checks.append({"check_id": check_id, "required": True, "passed": bool(passed), "details": details})

    identity = {key: checkpoint.get(key) for key in ("checkpoint_id", "protocol_id", "stage", "gate", "status")}
    check("p5_checkpoint_identity", identity == {"checkpoint_id": CHECKPOINT_ID, "protocol_id": "fusionagent.benchmark-platform-implementation-protocol.v1", "stage": "P5", "gate": "BP5", "status": "stage_validated_offline"}, identity)
    try:
        replay = _storage_replay()
        replay_passed = all(replay.values())
    except Exception as error:
        replay, replay_passed = {"error": f"{type(error).__name__}: {error}"}, False
    check("interrupt_duplicate_and_tamper_replay", replay_passed, replay)

    forbidden_imports = {"requests", "httpx", "urllib", "socket", "openai", "anthropic", "neo4j", "llm", "celery", "redis"}
    tree = ast.parse((repo_root / "benchmark_platform/store.py").read_text(encoding="utf-8"), filename="benchmark_platform/store.py")
    import_hits: list[str] = []
    for node in ast.walk(tree):
        names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
        import_hits.extend(name for name in names if name.split(".", 1)[0] in forbidden_imports)
    check("offline_store_import_boundary", not import_hits, {"forbidden_imports": import_hits})

    errors: list[str] = []
    for item in checkpoint.get("files", []):
        path = repo_root / str(item.get("path", ""))
        if not path.is_file() or file_hash(path) != item.get("sha256"):
            errors.append(str(item.get("path")))
    check("p5_artifact_hashes", not errors and bool(checkpoint.get("files")), {"errors": errors, "count": len(checkpoint.get("files", []))})
    check("zero_calls_and_no_future_output_root", checkpoint.get("accounting") == ACCOUNTING and not Path(checkpoint["paths"]["future_output_root"]).exists(), {"accounting": checkpoint.get("accounting"), "future_output_root": checkpoint["paths"]["future_output_root"]})
    check("next_gate_boundary", checkpoint.get("next_stage") == {"stage": "P6", "gate": "BP6", "automatic_progression": False}, checkpoint.get("next_stage"))
    failures = [item["check_id"] for item in checks if item["required"] and not item["passed"]]
    return {"audit_id": AUDIT_ID, "checkpoint_id": CHECKPOINT_ID, "protocol_id": "fusionagent.benchmark-platform-implementation-protocol.v1", "stage": "P5", "gate": "BP5", "checks": checks, "required_check_count": len(checks), "passed_required_check_count": len(checks) - len(failures), "required_failures": failures, "overall_passed": not failures, "stage_status": "complete" if not failures else "blocked_at_p5", "accounting": ACCOUNTING, "next_stage": "P6/BP6" if not failures else None, "automatic_progression": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the bounded benchmark platform P5 stage.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    checkpoint = args.checkpoint if args.checkpoint.is_absolute() else root / args.checkpoint
    output = args.output if args.output.is_absolute() else root / args.output
    result = audit_p5(root, checkpoint)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"overall_passed": result["overall_passed"], "required_failures": result["required_failures"]}))
    return 0 if result["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
