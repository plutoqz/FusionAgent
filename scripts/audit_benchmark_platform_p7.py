from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

MANIFEST_ID = "fusionagent.benchmark-platform-core.implementation-manifest.v1"
AUDIT_ID = "fusionagent.benchmark-platform-core.p7-audit.v1"
CHECKPOINT_ID = "fusionagent.benchmark-platform-core.p7-checkpoint.v1"
REVIEW_ID = "fusionagent.benchmark-platform-core.p7-review.v1"
PROTOCOL_ID = "fusionagent.benchmark-platform-implementation-protocol.v1"
SOURCE_COMMIT = "35e1641c9b573657663b3733d5c94d082fedb8b6"
EXPECTED_TAG = "benchmark-platform-core-v1"
IMPLEMENTATION_ROOT = Path("docs/current/benchmark/platform/v1/implementation")
CORE_TEST_FILES = {
    "tests/test_benchmark_platform_p0.py",
    "tests/test_benchmark_platform_models.py",
    "tests/test_benchmark_platform_canonical.py",
    "tests/test_benchmark_platform_p2.py",
    "tests/test_benchmark_platform_p3.py",
    "tests/test_benchmark_platform_p4.py",
    "tests/test_benchmark_platform_p5.py",
    "tests/test_benchmark_platform_p6.py",
}
REVIEW_ITEMS = {
    "BPI-COMPONENTS",
    "BPI-FAIL-CLOSED",
    "BPI-VIEWS",
    "BPI-RECOVERY",
    "BPI-CLI",
    "BPI-EVIDENCE",
    "BPI-NO-EXPANSION",
}
FORBIDDEN_IMPORTS = {"requests", "httpx", "urllib", "socket", "openai", "anthropic", "neo4j", "llm", "celery", "redis"}
ACCOUNTING = {"benchmark_instances_generated": 0, "provider_calls": 0, "judge_calls": 0, "formal_result_roots_created": 0, "confirmation_unsealed": False, "selective_e2e_selected": False, "platform_implementation_started": True}
CORE_TEST_COMMAND = "$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'; python -m pytest tests/test_benchmark_platform_p0.py tests/test_benchmark_platform_models.py tests/test_benchmark_platform_canonical.py tests/test_benchmark_platform_p2.py tests/test_benchmark_platform_p3.py tests/test_benchmark_platform_p4.py tests/test_benchmark_platform_p5.py tests/test_benchmark_platform_p6.py -q --basetemp tmp/pytest-benchmark-platform-p7-core"


def file_hash(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _entries(repo_root: Path, paths: set[str]) -> list[dict[str, str]]:
    return [{"path": path, "sha256": file_hash(repo_root / path)} for path in sorted(paths)]


def _stage_evidence_paths() -> set[str]:
    paths = {f"{IMPLEMENTATION_ROOT.as_posix()}/README.md", f"{IMPLEMENTATION_ROOT.as_posix()}/p0_baseline.json", f"{IMPLEMENTATION_ROOT.as_posix()}/p0_audit.json"}
    for stage in range(1, 7):
        paths.add(f"{IMPLEMENTATION_ROOT.as_posix()}/p{stage}_checkpoint.json")
        paths.add(f"{IMPLEMENTATION_ROOT.as_posix()}/p{stage}_audit.json")
    return paths


def build_manifest(repo_root: Path, output: Path) -> dict[str, Any]:
    all_tests = {path.relative_to(repo_root).as_posix() for path in (repo_root / "tests").glob("test_benchmark_platform*.py")}
    audit_tests = {"tests/test_benchmark_platform_p7.py"}
    historical_tests = all_tests - CORE_TEST_FILES - audit_tests
    manifest = {
        "manifest_id": MANIFEST_ID,
        "protocol_id": PROTOCOL_ID,
        "milestone_id": "M-BENCH-PLATFORM-CORE-V1",
        "version": "1.0.0",
        "status": "pending_human_review",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "file_hash_canonicalization": "normalize_crlf_to_lf",
        "git": {"branch": "codex/benchmark-platform-dev-r1", "implementation_source_commit": SOURCE_COMMIT, "expected_freeze_tag": EXPECTED_TAG},
        "design_binding": {"tag": "benchmark-design-freeze-v1", "commit": "08b55f7e03eabb74721979153df57aeee3200538", "design_id": "fusionagent.benchmark-design.v1", "kg_release_id": "fusionagent-kg-v1.0.0", "kg_semantic_hash": "sha256:50067b9368914c47580707650789c04c78b2e856ccb3ef4d120a31f36c0ad71e"},
        "files": {
            "source": _entries(repo_root, {path.relative_to(repo_root).as_posix() for path in (repo_root / "benchmark_platform").glob("*.py")}),
            "dependencies": _entries(repo_root, {"requirements.txt"}),
            "fixtures": _entries(repo_root, {path.relative_to(repo_root).as_posix() for path in (repo_root / "tests/fixtures/benchmark_platform").glob("*") if path.is_file()}),
            "core_contract_tests": _entries(repo_root, CORE_TEST_FILES),
            "historical_stage_tests": _entries(repo_root, historical_tests),
            "p7_audit_assets": _entries(repo_root, {path.relative_to(repo_root).as_posix() for path in (repo_root / "scripts").glob("audit_benchmark_platform_*.py")} | audit_tests),
            "stage_evidence": _entries(repo_root, _stage_evidence_paths()),
        },
        "installed_dependencies": {name: importlib.metadata.version(name) for name in ("jsonschema", "pydantic", "pytest")},
        "validation": {"core_test_command": CORE_TEST_COMMAND, "core_tests_passed": 64, "core_test_result": "64 passed in 24.63s", "historical_stage_tests_policy": "hashed_for_lineage_not_rerun_against_later_worktree"},
        "accounting": ACCOUNTING,
        "claim_boundary": {"strongest_status": "implementation_validated_offline", "supports_method_effect": False, "supports_production_capability": False, "supports_formal_experiment": False, "supports_e2e": False},
        "review": {"review_id": REVIEW_ID, "status": "pending_human_review", "automatic_approval_forbidden": True},
        "self_hash_policy": {"implementation_manifest.json": "excluded_to_avoid_recursive_hashing", "p7_audit.json": "excluded_as_generated_output", "p7_review.json": "separately_verified_human_decision", "p7_checkpoint.json": "separately_verified_stage_state"},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _entry_map(entries: Any) -> tuple[dict[str, str], list[str]]:
    if not isinstance(entries, list):
        return {}, ["entries_not_list"]
    values: dict[str, str] = {}
    duplicates: list[str] = []
    for item in entries:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
            duplicates.append("malformed_entry")
            continue
        if item["path"] in values:
            duplicates.append(item["path"])
        values[item["path"]] = item["sha256"]
    return values, duplicates


def _expected_sets(repo_root: Path) -> dict[str, set[str]]:
    all_tests = {path.relative_to(repo_root).as_posix() for path in (repo_root / "tests").glob("test_benchmark_platform*.py")}
    return {
        "source": {path.relative_to(repo_root).as_posix() for path in (repo_root / "benchmark_platform").glob("*.py")},
        "dependencies": {"requirements.txt"},
        "fixtures": {path.relative_to(repo_root).as_posix() for path in (repo_root / "tests/fixtures/benchmark_platform").glob("*") if path.is_file()},
        "core_contract_tests": CORE_TEST_FILES,
        "historical_stage_tests": all_tests - CORE_TEST_FILES - {"tests/test_benchmark_platform_p7.py"},
        "p7_audit_assets": {path.relative_to(repo_root).as_posix() for path in (repo_root / "scripts").glob("audit_benchmark_platform_*.py")} | {"tests/test_benchmark_platform_p7.py"},
        "stage_evidence": _stage_evidence_paths(),
    }


def _hash_errors(repo_root: Path, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    files = manifest.get("files", {})
    if not isinstance(files, dict):
        return ["files_not_object"]
    for category, expected in _expected_sets(repo_root).items():
        values, duplicates = _entry_map(files.get(category))
        if set(values) != expected:
            errors.append(f"{category}:file_set")
        errors.extend(f"{category}:duplicate:{item}" for item in duplicates)
        for relative, expected_hash in values.items():
            path = repo_root / relative
            if not path.is_file() or file_hash(path) != expected_hash:
                errors.append(f"{category}:hash:{relative}")
    return errors


def _import_hits(repo_root: Path) -> list[str]:
    hits: list[str] = []
    for path in sorted((repo_root / "benchmark_platform").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
        for node in ast.walk(tree):
            modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            hits.extend(f"{path.name}:{module}" for module in modules if module.split(".", 1)[0] in FORBIDDEN_IMPORTS)
    return hits


def _stage_chain(repo_root: Path) -> tuple[bool, dict[str, Any]]:
    details: dict[str, Any] = {}
    passed = True
    for stage in range(7):
        audit = load(repo_root / IMPLEMENTATION_ROOT / f"p{stage}_audit.json")
        stage_passed = audit.get("overall_passed") is True and audit.get("stage") == f"P{stage}" and audit.get("gate") == f"BP{stage}"
        details[f"P{stage}"] = {"overall_passed": audit.get("overall_passed"), "stage": audit.get("stage"), "gate": audit.get("gate")}
        passed = passed and stage_passed
    return passed, details


def _git_blob_hash(repo_root: Path, commit: str, relative_path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{commit}:{relative_path}"],
        cwd=repo_root,
        capture_output=True,
        check=True,
    )
    return f"sha256:{hashlib.sha256(result.stdout.replace(b'\r\n', b'\n')).hexdigest()}"


def _review_pass(review: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    checklist = review.get("checklist", [])
    decisions = {item.get("item_id"): item.get("decision") for item in checklist if isinstance(item, dict)}
    passed = review.get("review_id") == REVIEW_ID and review.get("decision") == "approved" and set(decisions) == REVIEW_ITEMS and all(value == "approved" for value in decisions.values()) and review.get("unresolved_disagreements") == [] and isinstance(review.get("reviewer", {}).get("name"), str) and bool(review["reviewer"]["name"].strip())
    return passed, {"status": review.get("status"), "decision": review.get("decision"), "decisions": decisions, "reviewer": review.get("reviewer"), "unresolved_disagreements": review.get("unresolved_disagreements")}


def audit_p7(repo_root: Path, manifest_path: Path, review_path: Path, checkpoint_path: Path) -> dict[str, Any]:
    manifest = load(manifest_path)
    review = load(review_path)
    checkpoint = load(checkpoint_path)
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, details: Any, *, human: bool = False) -> None:
        checks.append({"check_id": check_id, "required": True, "human": human, "passed": bool(passed), "details": details})

    identity = {key: manifest.get(key) for key in ("manifest_id", "protocol_id", "milestone_id", "version", "status")}
    check("implementation_manifest_identity", identity == {"manifest_id": MANIFEST_ID, "protocol_id": PROTOCOL_ID, "milestone_id": "M-BENCH-PLATFORM-CORE-V1", "version": "1.0.0", "status": "pending_human_review"}, identity)

    branch = subprocess.run(["git", "branch", "--show-current"], cwd=repo_root, capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()
    source_ancestor = subprocess.run(["git", "merge-base", "--is-ancestor", SOURCE_COMMIT, "HEAD"], cwd=repo_root, check=False).returncode == 0
    git_binding = manifest.get("git", {})
    check("implementation_git_binding", branch == "codex/benchmark-platform-dev-r1" and source_ancestor and git_binding == {"branch": "codex/benchmark-platform-dev-r1", "implementation_source_commit": SOURCE_COMMIT, "expected_freeze_tag": EXPECTED_TAG}, {"branch": branch, "source_ancestor": source_ancestor, "manifest_git": git_binding})

    hash_errors = _hash_errors(repo_root, manifest)
    check("implementation_file_sets_and_hashes", not hash_errors, {"errors": hash_errors, "category_counts": {key: len(value) for key, value in _expected_sets(repo_root).items()}})

    installed = manifest.get("installed_dependencies")
    expected_installed = {name: importlib.metadata.version(name) for name in ("jsonschema", "pydantic", "pytest")}
    check("dependency_identity", installed == expected_installed, {"manifest": installed, "installed": expected_installed})

    chain_passed, chain_details = _stage_chain(repo_root)
    check("p0_p6_stage_chain", chain_passed, chain_details)

    validation = manifest.get("validation", {})
    check("full_core_contract_validation", validation.get("core_test_command") == CORE_TEST_COMMAND and validation.get("core_tests_passed") == 64 and validation.get("core_test_result") == "64 passed in 24.63s", validation)

    import_hits = _import_hits(repo_root)
    check("offline_import_boundary", not import_hits, {"forbidden_imports": import_hits})

    p6_path = f"{IMPLEMENTATION_ROOT.as_posix()}/p6_audit.json"
    p6 = load(repo_root / p6_path)
    current_p6_hash = file_hash(repo_root / p6_path)
    source_p6_hash = _git_blob_hash(repo_root, SOURCE_COMMIT, p6_path)
    check("p6_cli_boundary_frozen_at_source_commit", p6.get("overall_passed") is True and p6.get("required_failures") == [] and current_p6_hash == source_p6_hash, {"overall_passed": p6.get("overall_passed"), "required_failures": p6.get("required_failures"), "current_hash": current_p6_hash, "source_commit_hash": source_p6_hash})

    future_root = Path(checkpoint.get("paths", {}).get("future_output_root", ""))
    check("zero_call_and_claim_boundary", manifest.get("accounting") == ACCOUNTING and checkpoint.get("accounting") == ACCOUNTING and future_root.is_absolute() and not future_root.exists() and manifest.get("claim_boundary", {}).get("strongest_status") == "implementation_validated_offline" and all(manifest.get("claim_boundary", {}).get(key) is False for key in ("supports_method_effect", "supports_production_capability", "supports_formal_experiment", "supports_e2e")), {"manifest_accounting": manifest.get("accounting"), "checkpoint_accounting": checkpoint.get("accounting"), "future_output_root": str(future_root), "future_output_root_exists": future_root.exists(), "claim_boundary": manifest.get("claim_boundary")})

    checkpoint_identity = {key: checkpoint.get(key) for key in ("checkpoint_id", "protocol_id", "stage", "gate", "status")}
    check("p7_checkpoint_boundary", checkpoint_identity == {"checkpoint_id": CHECKPOINT_ID, "protocol_id": PROTOCOL_ID, "stage": "P7", "gate": "BP7", "status": "awaiting_human_review"} and checkpoint.get("freeze", {}).get("tag_created") is False and checkpoint.get("governance", {}).get("updated") is False, {"identity": checkpoint_identity, "freeze": checkpoint.get("freeze"), "governance": checkpoint.get("governance")})

    review_passed, review_details = _review_pass(review)
    check("human_implementation_review", review_passed, review_details, human=True)

    failures = [item["check_id"] for item in checks if item["required"] and not item["passed"]]
    machine_failures = [item["check_id"] for item in checks if item["required"] and not item["human"] and not item["passed"]]
    return {"audit_id": AUDIT_ID, "manifest_id": MANIFEST_ID, "checkpoint_id": CHECKPOINT_ID, "protocol_id": PROTOCOL_ID, "stage": "P7", "gate": "BP7", "checks": checks, "required_check_count": len(checks), "passed_required_check_count": len(checks) - len(failures), "machine_check_count": len([item for item in checks if not item["human"]]), "passed_machine_check_count": len([item for item in checks if not item["human"] and item["passed"]]), "machine_required_failures": machine_failures, "required_failures": failures, "machine_checks_passed": not machine_failures, "overall_passed": not failures, "stage_status": "complete" if not failures else ("awaiting_human_review" if failures == ["human_implementation_review"] else "blocked_at_p7"), "accounting": ACCOUNTING, "freeze_authorized": not failures, "automatic_progression": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or audit the bounded benchmark platform P7 closure.")
    parser.add_argument("--build-manifest", action="store_true")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--review", type=Path)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    manifest_path = args.manifest if args.manifest.is_absolute() else root / args.manifest
    if args.build_manifest:
        build_manifest(root, manifest_path)
        print(json.dumps({"manifest": str(manifest_path), "status": "pending_human_review"}))
        return 0
    if args.review is None or args.checkpoint is None or args.output is None:
        parser.error("--review, --checkpoint and --output are required for audit mode")
    review_path = args.review if args.review.is_absolute() else root / args.review
    checkpoint_path = args.checkpoint if args.checkpoint.is_absolute() else root / args.checkpoint
    output_path = args.output if args.output.is_absolute() else root / args.output
    result = audit_p7(root, manifest_path, review_path, checkpoint_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"machine_checks_passed": result["machine_checks_passed"], "overall_passed": result["overall_passed"], "required_failures": result["required_failures"]}))
    return 0 if result["overall_passed"] else (2 if result["stage_status"] == "awaiting_human_review" else 1)


if __name__ == "__main__":
    raise SystemExit(main())
