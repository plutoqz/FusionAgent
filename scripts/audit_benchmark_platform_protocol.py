from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote


AUDIT_ID = "fusionagent.benchmark-platform-protocol-audit.v1"
PROTOCOL_ID = "fusionagent.benchmark-platform-implementation-protocol.v1"
CONTRACT_ID = "fusionagent.benchmark-platform-component-contract.v1"
BASE_TAG = "benchmark-design-freeze-v1"
BASE_COMMIT = "08b55f7e03eabb74721979153df57aeee3200538"
PROTOCOL_BRANCH = "codex/benchmark-platform-protocol-r1"
PROTOCOL_ROOT = "docs/current/benchmark/platform/v1"
PLAN_PATH = "docs/current/benchmark-platform-implementation-protocol.md"
EXPECTED_ROOT_FILES = {
    "README.md",
    "component_contract.json",
    "protocol_manifest.json",
    "protocol_review.json",
    "protocol_audit.json",
}
EXPECTED_MANIFEST_FILES = {
    f"{PROTOCOL_ROOT}/README.md",
    f"{PROTOCOL_ROOT}/component_contract.json",
    f"{PROTOCOL_ROOT}/protocol_review.json",
    PLAN_PATH,
    "scripts/audit_benchmark_platform_protocol.py",
    "tests/test_benchmark_platform_protocol.py",
}
EXPECTED_FROZEN_INPUTS = {
    "docs/current/benchmark/v1/README.md",
    "docs/current/benchmark/v1/benchmark_charter.md",
    "docs/current/benchmark/v1/capability_matrix.json",
    "docs/current/benchmark/v1/template.schema.json",
    "docs/current/benchmark/v1/evaluation_contract.json",
    "docs/current/benchmark/v1/human_review_rubric.md",
    "docs/current/benchmark/v1/selection_governance.json",
    "docs/current/benchmark/v1/freeze_manifest.json",
    "docs/current/benchmark/v1/freeze_audit.json",
    "docs/current/benchmark/v1/protocol_review.json",
}
EXPECTED_COMPONENT_IDS = {
    "BP-DESIGN-LOADER",
    "BP-MODELS",
    "BP-CANONICAL",
    "BP-CROSSWALK",
    "BP-GENERATOR",
    "BP-RELATIONS",
    "BP-VIEWS",
    "BP-STORE",
    "BP-CLI",
}
EXPECTED_UNIT_TYPES = {
    "single",
    "counterfactual_pair",
    "invariant_set",
    "composition_family",
    "temporal_trace",
}
EXPECTED_CLI_COMMANDS = {
    "validate-design",
    "validate-template",
    "generate-development",
    "validate-run",
    "project-views",
    "audit-run",
    "resume-development",
}
EXPECTED_STATES = [
    "created",
    "design_bound",
    "templates_validated",
    "generated",
    "relations_validated",
    "views_projected",
    "audited",
    "development_complete",
]
EXPECTED_TEST_CATEGORIES = {
    "closed_schema",
    "canonical_hash",
    "design_tamper",
    "crosswalk",
    "deterministic_generation",
    "relation_negative",
    "view_leakage",
    "write_new",
    "checkpoint_resume",
    "no_network",
    "forbidden_import",
    "cli_exit_codes",
}
ALLOWED_CHANGED_PREFIXES = (
    f"{PROTOCOL_ROOT}/",
    PLAN_PATH,
    "scripts/audit_benchmark_platform_protocol.py",
    "tests/test_benchmark_platform_protocol.py",
    "docs/README.md",
    "docs/current/research-governance-index.md",
    "docs/current/research-experiment-ledger.md",
)


def canonical_file_sha256(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def git_output(repo_root: Path, *args: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", *args], cwd=repo_root, check=True, capture_output=True, text=text, encoding="utf-8" if text else None
    )
    return result.stdout


def git_tag_commit(repo_root: Path, tag: str) -> str:
    return str(git_output(repo_root, "rev-parse", f"{tag}^{{}}" )).strip()


def git_blob_sha256(repo_root: Path, commit: str, path: str) -> str:
    data = git_output(repo_root, "show", f"{commit}:{path}", text=False)
    assert isinstance(data, bytes)
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def changed_paths(repo_root: Path) -> list[str]:
    commands = [
        ("diff", "--name-only", BASE_COMMIT, "HEAD"),
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ]
    paths: set[str] = set()
    for command in commands:
        output = str(git_output(repo_root, *command))
        paths.update(line.strip().replace("\\", "/") for line in output.splitlines() if line.strip())
    return sorted(paths)


def local_markdown_link_errors(markdown_paths: Iterable[Path]) -> list[dict[str, str]]:
    pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    errors: list[dict[str, str]] = []
    for path in markdown_paths:
        for raw_target in pattern.findall(path.read_text(encoding="utf-8")):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            candidate = (path.parent / unquote(target.split("#", 1)[0])).resolve()
            if not candidate.exists():
                errors.append({"file": path.as_posix(), "target": raw_target})
    return errors


def hash_entry_map(items: Any) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    duplicates: list[str] = []
    if not isinstance(items, list):
        return values, duplicates
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("sha256"), str):
            continue
        path = item["path"]
        if path in values:
            duplicates.append(path)
        values[path] = item["sha256"]
    return values, sorted(set(duplicates))


def hash_errors(repo_root: Path, entries: dict[str, str]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for relative_path, expected in sorted(entries.items()):
        path = repo_root / relative_path
        if not path.is_file():
            errors.append({"path": relative_path, "error": "missing"})
            continue
        actual = canonical_file_sha256(path)
        if actual != expected:
            errors.append({"path": relative_path, "error": "hash_mismatch", "expected": expected, "actual": actual})
    return errors


def frozen_input_errors(repo_root: Path, entries: dict[str, str]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for relative_path, expected in sorted(entries.items()):
        actual = git_blob_sha256(repo_root, BASE_COMMIT, relative_path)
        if actual != expected:
            errors.append({"path": relative_path, "expected": expected, "actual": actual})
    return errors


def add_check(checks: list[dict[str, Any]], check_id: str, passed: bool, details: Any) -> None:
    checks.append({"check_id": check_id, "required": True, "passed": bool(passed), "details": details})


def audit_protocol(repo_root: Path, protocol_root: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    missing = sorted(name for name in EXPECTED_ROOT_FILES - {"protocol_audit.json"} if not (protocol_root / name).is_file())
    add_check(checks, "required_protocol_files", not missing, {"missing": missing})

    contract = load_json(protocol_root / "component_contract.json")
    manifest = load_json(protocol_root / "protocol_manifest.json")
    review = load_json(protocol_root / "protocol_review.json")
    plan_text = (repo_root / PLAN_PATH).read_text(encoding="utf-8")

    identities = {
        "contract_id": contract.get("component_contract_id"),
        "contract_protocol_id": contract.get("protocol_id"),
        "manifest_id": manifest.get("manifest_id"),
        "manifest_protocol_id": manifest.get("protocol_id"),
        "review_protocol_id": review.get("protocol_id"),
    }
    expected_identities = {
        "contract_id": CONTRACT_ID,
        "contract_protocol_id": PROTOCOL_ID,
        "manifest_id": "fusionagent.benchmark-platform-protocol-manifest.v1",
        "manifest_protocol_id": PROTOCOL_ID,
        "review_protocol_id": PROTOCOL_ID,
    }
    add_check(checks, "protocol_identities", identities == expected_identities, {"actual": identities, "expected": expected_identities})

    review_approved = (
        review.get("status") == "approved"
        and review.get("decision") == "approved"
        and review.get("reviewer", {}).get("role") in {"user", "independent_reviewer"}
        and review.get("reviewer", {}).get("independent_of_authoring") is True
        and review.get("checklist")
        and all(item.get("decision") == "approved" for item in review["checklist"])
        and review.get("unresolved_disagreements") == []
    )
    milestone = manifest.get("milestone", {})
    if review_approved:
        milestone_pass = (
            milestone.get("status") == "complete"
            and milestone.get("complete") is True
            and milestone.get("blocking_gate") is None
        )
    else:
        milestone_pass = (
            milestone.get("status") == "blocked_before_protocol_freeze"
            and milestone.get("complete") is False
            and milestone.get("blocking_gate") == "human_protocol_review"
        )
    manifest_git = manifest.get("git", {})
    manifest_identity_pass = (
        manifest.get("file_hash_canonicalization") == "normalize_crlf_to_lf"
        and manifest_git.get("branch") == PROTOCOL_BRANCH
        and manifest_git.get("base_tag") == BASE_TAG
        and manifest_git.get("base_commit") == BASE_COMMIT
        and milestone_pass
    )
    add_check(checks, "manifest_state", manifest_identity_pass, {"git": manifest_git, "milestone": milestone, "review_approved": review_approved})

    tag_commit = git_tag_commit(repo_root, BASE_TAG)
    binding = contract.get("design_binding", {})
    manifest_binding = manifest.get("design_binding", {})
    binding_pass = (
        tag_commit == BASE_COMMIT
        and binding.get("tag") == BASE_TAG
        and binding.get("commit") == BASE_COMMIT
        and binding.get("design_id") == "fusionagent.benchmark-design.v1"
        and binding.get("freeze_id") == "fusionagent.benchmark-design-freeze.v1"
        and binding.get("kg_release_id") == "fusionagent-kg-v1.0.0"
        and manifest_binding == binding
    )
    add_check(checks, "frozen_design_binding", binding_pass, {"tag_commit": tag_commit, "contract": binding, "manifest": manifest_binding})

    manifest_files, manifest_duplicates = hash_entry_map(manifest.get("files"))
    frozen_inputs, frozen_duplicates = hash_entry_map(manifest.get("frozen_inputs"))
    manifest_details = {
        "file_paths": sorted(manifest_files),
        "missing_files": sorted(EXPECTED_MANIFEST_FILES - set(manifest_files)),
        "unexpected_files": sorted(set(manifest_files) - EXPECTED_MANIFEST_FILES),
        "file_duplicates": manifest_duplicates,
        "frozen_input_paths": sorted(frozen_inputs),
        "missing_frozen_inputs": sorted(EXPECTED_FROZEN_INPUTS - set(frozen_inputs)),
        "unexpected_frozen_inputs": sorted(set(frozen_inputs) - EXPECTED_FROZEN_INPUTS),
        "frozen_duplicates": frozen_duplicates,
    }
    manifest_set_pass = (
        set(manifest_files) == EXPECTED_MANIFEST_FILES
        and set(frozen_inputs) == EXPECTED_FROZEN_INPUTS
        and not manifest_duplicates
        and not frozen_duplicates
    )
    add_check(checks, "protocol_manifest_contract", manifest_set_pass, manifest_details)
    file_hash_errors = hash_errors(repo_root, manifest_files)
    input_hash_errors = frozen_input_errors(repo_root, frozen_inputs)
    add_check(checks, "protocol_file_hashes", not file_hash_errors, {"errors": file_hash_errors})
    add_check(checks, "frozen_input_hashes", not input_hash_errors, {"errors": input_hash_errors})

    mapping = contract.get("research_mapping", {})
    mapping_pass = (
        set(mapping.get("objectives", [])) == {"O2", "O3"}
        and set(mapping.get("research_questions", [])) == {"RQ2", "RQ3"}
        and set(mapping.get("innovations", [])) == {"I2", "I4"}
        and set(mapping.get("candidate_claim_ids", []))
        == {"CL-BENCH-CAUSAL", "CL-BENCH-INVARIANT", "CL-BENCH-COMPOSE", "CL-BENCH-RECOVERY", "CL-BENCH-DIAG"}
        and mapping.get("new_research_claim_created") is False
        and mapping.get("scheme_b_role_changed") is False
    )
    add_check(checks, "research_mapping", mapping_pass, mapping)

    components = contract.get("components", [])
    component_ids = [item.get("component_id") for item in components]
    incomplete_components = [
        item.get("component_id")
        for item in components
        if not all(item.get(key) for key in ("module", "responsibility", "inputs", "outputs", "fail_closed_on", "forbidden_dependencies"))
    ]
    add_check(
        checks,
        "component_contract",
        set(component_ids) == EXPECTED_COMPONENT_IDS and len(component_ids) == len(set(component_ids)) and not incomplete_components,
        {"component_ids": component_ids, "incomplete": incomplete_components},
    )

    identity = contract.get("implementation_identity", {})
    paths_pass = (
        identity.get("package") == "benchmark_platform"
        and identity.get("branch") == "codex/benchmark-platform-dev-r1"
        and identity.get("milestone") == "M-BENCH-PLATFORM-CORE-V1"
        and identity.get("authorization_required_after_protocol_freeze") is True
        and identity.get("strongest_completion_status") == "implementation_validated_offline"
        and "docs/current/benchmark/v1/" in contract.get("forbidden_change_prefixes", [])
        and "schemas/benchmark.py" in contract.get("forbidden_change_prefixes", [])
        and contract.get("dependency_policy", {}).get("allowed_additions") == ["jsonschema>=4.23,<5"]
        and contract.get("dependency_policy", {}).get("all_other_dependency_changes_forbidden") is True
    )
    add_check(checks, "implementation_boundary", paths_pass, {"identity": identity, "allowed": contract.get("allowed_change_paths"), "forbidden": contract.get("forbidden_change_prefixes")})

    cli_commands = contract.get("allowed_cli_commands", [])
    forbidden_cli_tokens = set(contract.get("forbidden_cli_tokens", []))
    cli_violations = [command for command in cli_commands if any(token in command for token in forbidden_cli_tokens)]
    stages = contract.get("implementation_stages", [])
    stage_pairs = [(item.get("stage_id"), item.get("gate")) for item in stages]
    mechanics_pass = (
        set(contract.get("experiment_unit_types", [])) == EXPECTED_UNIT_TYPES
        and set(cli_commands) == EXPECTED_CLI_COMMANDS
        and not cli_violations
        and contract.get("state_machine") == EXPECTED_STATES
        and contract.get("terminal_failure_state") == "failed_retained"
        and stage_pairs == [(f"P{i}", f"BP{i}") for i in range(8)]
        and set(contract.get("test_contract", {}).get("required_categories", [])) == EXPECTED_TEST_CATEGORIES
        and contract.get("test_contract", {}).get("contract_fixtures_are_benchmark_instances") is False
        and contract.get("test_contract", {}).get("fixture_claim_eligible") is False
    )
    add_check(checks, "platform_mechanics_contract", mechanics_pass, {"units": contract.get("experiment_unit_types"), "cli": cli_commands, "cli_violations": cli_violations, "states": contract.get("state_machine"), "stages": stage_pairs})

    expected_accounting = {
        "benchmark_instances_generated": 0,
        "provider_calls": 0,
        "judge_calls": 0,
        "formal_result_roots_created": 0,
        "confirmation_unsealed": False,
        "selective_e2e_selected": False,
        "platform_implementation_started": False,
    }
    accounting = contract.get("accounting", {})
    add_check(checks, "zero_call_accounting", accounting == expected_accounting and manifest.get("accounting") == expected_accounting, {"contract": accounting, "manifest": manifest.get("accounting")})

    plan_tokens = {
        "M-BENCH-PLATFORM-PROTOCOL-V1",
        "M-BENCH-PLATFORM-CORE-V1",
        "implementation_validated_offline",
        "benchmark_platform/",
        "development-only",
        "P0",
        "P7",
        "Provider",
        "LLM judge",
        "benchmark V1.1/V2",
        "明确实施指令",
    }
    missing_plan_tokens = sorted(token for token in plan_tokens if token not in plan_text)
    add_check(checks, "implementation_plan_completeness", not missing_plan_tokens, {"missing_tokens": missing_plan_tokens})

    paths = changed_paths(repo_root)
    forbidden_paths = [path for path in paths if not any(path == prefix or path.startswith(prefix) for prefix in ALLOWED_CHANGED_PREFIXES)]
    implementation_exists = (repo_root / "benchmark_platform").exists()
    add_check(checks, "bounded_protocol_change_set", not forbidden_paths and not implementation_exists, {"changed_paths": paths, "forbidden_paths": forbidden_paths, "implementation_directory_exists": implementation_exists})

    actual_root_files = {path.name for path in protocol_root.iterdir() if path.is_file()}
    nested_dirs = sorted(path.relative_to(protocol_root).as_posix() for path in protocol_root.rglob("*") if path.is_dir())
    add_check(checks, "protocol_directory_inventory", not (actual_root_files - EXPECTED_ROOT_FILES) and not nested_dirs, {"files": sorted(actual_root_files), "unexpected": sorted(actual_root_files - EXPECTED_ROOT_FILES), "nested_directories": nested_dirs})

    markdown_errors = local_markdown_link_errors([protocol_root / "README.md", repo_root / PLAN_PATH])
    add_check(checks, "markdown_links", not markdown_errors, {"errors": markdown_errors})

    review_items = review.get("checklist", [])
    review_pass = bool(review_approved)
    add_check(checks, "human_protocol_review", review_pass, {"status": review.get("status"), "decision": review.get("decision"), "reviewer": review.get("reviewer"), "pending_items": [item.get("item_id") for item in review_items if item.get("decision") != "approved"]})

    failures = [item["check_id"] for item in checks if item["required"] and not item["passed"]]
    return {
        "audit_id": AUDIT_ID,
        "protocol_id": PROTOCOL_ID,
        "generated_at": manifest.get("audit_generated_at"),
        "repo_root": ".",
        "protocol_root": PROTOCOL_ROOT,
        "base_tag": BASE_TAG,
        "base_commit": BASE_COMMIT,
        "checks": checks,
        "required_check_count": len(checks),
        "passed_required_check_count": len(checks) - len(failures),
        "required_failures": failures,
        "overall_passed": not failures,
        "milestone_status": "complete" if not failures else "blocked_before_protocol_freeze",
        "accounting": expected_accounting,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the FusionAgent benchmark platform implementation protocol.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    protocol_root = args.root if args.root.is_absolute() else repo_root / args.root
    output = args.output if args.output.is_absolute() else repo_root / args.output
    result = audit_protocol(repo_root.resolve(), protocol_root.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"overall_passed": result["overall_passed"], "required_failures": result["required_failures"]}))
    return 0 if result["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
