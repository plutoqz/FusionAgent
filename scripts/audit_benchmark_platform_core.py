from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any


AUDIT_ID = "fusionagent.benchmark-platform-core-audit.v1"
BASELINE_ID = "fusionagent.benchmark-platform-core.p0-baseline.v1"
PROTOCOL_ID = "fusionagent.benchmark-platform-implementation-protocol.v1"
PROTOCOL_TAG = "benchmark-platform-protocol-v1"
PROTOCOL_COMMIT = "4db9f51f261d61ecb5c17b726d9897a09773eec2"
P0_COMMIT = "e71c1064e4d5e60e5c1ef76829a65a314d3e8544"
IMPLEMENTATION_BRANCH = "codex/benchmark-platform-dev-r1"
IMPLEMENTATION_ROOT = "docs/current/benchmark/platform/v1/implementation"
BASELINE_PATH = f"{IMPLEMENTATION_ROOT}/p0_baseline.json"
AUDIT_PATH = f"{IMPLEMENTATION_ROOT}/p0_audit.json"
EXPECTED_ACCOUNTING = {
    "benchmark_instances_generated": 0,
    "provider_calls": 0,
    "judge_calls": 0,
    "formal_result_roots_created": 0,
    "confirmation_unsealed": False,
    "selective_e2e_selected": False,
    "platform_implementation_started": False,
}
EXPECTED_P0_FILES = {
    f"{IMPLEMENTATION_ROOT}/README.md",
    BASELINE_PATH,
    AUDIT_PATH,
    "scripts/audit_benchmark_platform_core.py",
    "tests/test_benchmark_platform_p0.py",
}
EXPECTED_PLATFORM_TEST_COMMAND = (
    "python -m pytest tests -q -k benchmark_platform "
    "--ignore=tests/test_benchmark_platform_protocol.py "
    "--basetemp tmp/pytest-benchmark-platform-core"
)
PROCESS_COMMAND_PATTERN = (
    "FusionAgent-benchmark-platform-dev|benchmark_platform|"
    "audit_benchmark_platform_core|test_benchmark_platform"
)
P1_CHECKPOINT_PATH = f"{IMPLEMENTATION_ROOT}/p1_checkpoint.json"
P1_AUDIT_PATH = f"{IMPLEMENTATION_ROOT}/p1_audit.json"
P1_HASHED_FILES = {
    "benchmark_platform/__init__.py",
    "benchmark_platform/canonical.py",
    "benchmark_platform/models.py",
    "requirements.txt",
    "scripts/audit_benchmark_platform_core.py",
    "tests/fixtures/benchmark_platform/README.md",
    "tests/fixtures/benchmark_platform/template_contract_valid.json",
    "tests/test_benchmark_platform_canonical.py",
    "tests/test_benchmark_platform_models.py",
    "tests/test_benchmark_platform_p0.py",
    "tests/test_benchmark_platform_p1_audit.py",
}
EXPECTED_P1_FILES = EXPECTED_P0_FILES | P1_HASHED_FILES | {P1_CHECKPOINT_PATH, P1_AUDIT_PATH}
P1_ACCOUNTING = {
    "benchmark_instances_generated": 0,
    "provider_calls": 0,
    "judge_calls": 0,
    "formal_result_roots_created": 0,
    "confirmation_unsealed": False,
    "selective_e2e_selected": False,
    "platform_implementation_started": True,
}


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
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=text,
        encoding="utf-8" if text else None,
    )
    return result.stdout


def git_blob_sha256(repo_root: Path, revision: str, relative_path: str) -> str:
    data = git_output(repo_root, "show", f"{revision}:{relative_path}", text=False)
    assert isinstance(data, bytes)
    return f"sha256:{hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()}"


def changed_paths(repo_root: Path) -> list[str]:
    commands = [
        ("diff", "--name-only", PROTOCOL_TAG, "HEAD"),
        ("diff", "--name-only"),
        ("diff", "--cached", "--name-only"),
        ("ls-files", "--others", "--exclude-standard"),
    ]
    paths: set[str] = set()
    for command in commands:
        output = str(git_output(repo_root, *command))
        paths.update(line.strip().replace("\\", "/") for line in output.splitlines() if line.strip())
    return sorted(paths)


def is_allowed_p0_path(path: str) -> bool:
    return path in EXPECTED_P0_FILES


def installed_versions(names: list[str]) -> dict[str, str]:
    return {name: importlib.metadata.version(name) for name in names}


def matching_processes() -> list[dict[str, Any]]:
    if os.name != "nt":
        return []
    script = (
        f"$excluded={os.getpid()}; "
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.ProcessId -ne $excluded -and "
        "$_.Name -match '^(python|pythonw|uvicorn|celery|node)(\\.exe)?$' -and "
        f"$_.CommandLine -match '{PROCESS_COMMAND_PATTERN}' }} | "
        "Select-Object ProcessId,Name,CommandLine | ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if not result.stdout.strip():
        return []
    value = json.loads(result.stdout)
    return value if isinstance(value, list) else [value]


def add_check(checks: list[dict[str, Any]], check_id: str, passed: bool, details: Any) -> None:
    checks.append({"check_id": check_id, "required": True, "passed": bool(passed), "details": details})


def audit_p0(repo_root: Path, baseline_path: Path, probe_processes: bool = True) -> dict[str, Any]:
    baseline = load_json(baseline_path)
    checks: list[dict[str, Any]] = []

    baseline_identity = {
        "baseline_id": baseline.get("baseline_id"),
        "protocol_id": baseline.get("protocol_id"),
        "milestone_id": baseline.get("milestone_id"),
        "stage": baseline.get("stage"),
        "gate": baseline.get("gate"),
        "status": baseline.get("status"),
    }
    expected_identity = {
        "baseline_id": BASELINE_ID,
        "protocol_id": PROTOCOL_ID,
        "milestone_id": "M-BENCH-PLATFORM-CORE-V1",
        "stage": "P0",
        "gate": "BP0",
        "status": "captured",
    }
    add_check(checks, "p0_baseline_identity", baseline_identity == expected_identity, baseline_identity)

    git_state = baseline.get("git", {})
    tag_commit = str(git_output(repo_root, "rev-list", "-n", "1", PROTOCOL_TAG)).strip()
    branch = str(git_output(repo_root, "branch", "--show-current")).strip()
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", PROTOCOL_TAG, "HEAD"], cwd=repo_root, check=False
    ).returncode == 0
    git_pass = (
        tag_commit == PROTOCOL_COMMIT
        and branch == IMPLEMENTATION_BRANCH
        and git_state.get("branch") == IMPLEMENTATION_BRANCH
        and git_state.get("protocol_tag") == PROTOCOL_TAG
        and git_state.get("protocol_commit") == PROTOCOL_COMMIT
        and git_state.get("starting_head") == PROTOCOL_COMMIT
        and git_state.get("working_tree_clean_at_capture") is True
        and git_state.get("status_at_capture") == []
        and ancestor
    )
    add_check(
        checks,
        "protocol_tag_inheritance",
        git_pass,
        {"tag_commit": tag_commit, "branch": branch, "tag_is_ancestor": ancestor, "capture": git_state},
    )

    protocol_audit = load_json(repo_root / "docs/current/benchmark/platform/v1/protocol_audit.json")
    protocol_review = load_json(repo_root / "docs/current/benchmark/platform/v1/protocol_review.json")
    contract = load_json(repo_root / "docs/current/benchmark/platform/v1/component_contract.json")
    protocol_pass = (
        protocol_audit.get("overall_passed") is True
        and protocol_audit.get("passed_required_check_count") == 17
        and protocol_audit.get("required_check_count") == 17
        and protocol_review.get("status") == "approved"
        and protocol_review.get("decision") == "approved"
        and protocol_review.get("unresolved_disagreements") == []
        and contract.get("status") == "frozen_complete"
        and contract.get("implementation_identity", {}).get("branch") == IMPLEMENTATION_BRANCH
    )
    add_check(
        checks,
        "frozen_protocol_approved",
        protocol_pass,
        {
            "audit_overall": protocol_audit.get("overall_passed"),
            "audit_count": protocol_audit.get("passed_required_check_count"),
            "review_status": protocol_review.get("status"),
            "contract_status": contract.get("status"),
        },
    )

    frozen_errors: list[dict[str, str]] = []
    for item in baseline.get("frozen_inputs", []):
        relative_path = item.get("path")
        expected_hash = item.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
            frozen_errors.append({"path": str(relative_path), "error": "invalid_entry"})
            continue
        current_hash = canonical_file_sha256(repo_root / relative_path)
        tag_hash = git_blob_sha256(repo_root, PROTOCOL_TAG, relative_path)
        if current_hash != expected_hash or tag_hash != expected_hash:
            frozen_errors.append(
                {"path": relative_path, "expected": expected_hash, "current": current_hash, "tag": tag_hash}
            )
    add_check(checks, "frozen_input_hashes", not frozen_errors, {"errors": frozen_errors})

    release = load_json(repo_root / "kg/ontology/v1.0.0/release.json")
    binding = baseline.get("design_binding", {})
    design_pass = (
        binding.get("design_tag") == "benchmark-design-freeze-v1"
        and binding.get("design_commit") == "08b55f7e03eabb74721979153df57aeee3200538"
        and binding.get("design_id") == "fusionagent.benchmark-design.v1"
        and binding.get("kg_release_id") == release.get("release_id") == "fusionagent-kg-v1.0.0"
        and binding.get("kg_semantic_hash")
        == release.get("semantic_hash")
        == "sha256:50067b9368914c47580707650789c04c78b2e856ccb3ef4d120a31f36c0ad71e"
    )
    add_check(checks, "design_and_kg_binding", design_pass, {"baseline": binding, "release": release})

    environment = baseline.get("environment", {})
    package_names = sorted(environment.get("installed_packages", {}))
    actual_environment = {
        "python_executable": sys.executable,
        "python_version": platform.python_version(),
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "pip_version": subprocess.run(
            [sys.executable, "-m", "pip", "--version"], check=True, capture_output=True, text=True
        ).stdout.strip(),
        "git_version": str(git_output(repo_root, "--version")).strip(),
        "installed_packages": installed_versions(package_names),
    }
    add_check(checks, "environment_binding", environment == actual_environment, {"actual": actual_environment})

    paths = changed_paths(repo_root)
    forbidden_paths = [path for path in paths if not is_allowed_p0_path(path)]
    missing_expected = sorted(
        path for path in EXPECTED_P0_FILES - {AUDIT_PATH} if not (repo_root / path).is_file()
    )
    boundary_pass = not forbidden_paths and not missing_expected and not (repo_root / "benchmark_platform").exists()
    add_check(
        checks,
        "p0_change_boundary",
        boundary_pass,
        {
            "changed_paths": paths,
            "forbidden_paths": forbidden_paths,
            "missing_expected": missing_expected,
            "package_exists": (repo_root / "benchmark_platform").exists(),
        },
    )

    path_contract = baseline.get("paths", {})
    output_root = Path(str(path_contract.get("future_output_root", "")))
    output_pass = (
        path_contract.get("package") == "benchmark_platform"
        and path_contract.get("package_exists_at_capture") is False
        and path_contract.get("future_output_root_exists_at_capture") is False
        and output_root.is_absolute()
        and not output_root.exists()
    )
    add_check(checks, "future_output_root_absent", output_pass, {"path": str(output_root), "exists": output_root.exists()})

    accounting = baseline.get("accounting", {})
    contract_accounting = contract.get("accounting", {})
    add_check(
        checks,
        "zero_call_accounting",
        accounting == EXPECTED_ACCOUNTING and contract_accounting == EXPECTED_ACCOUNTING,
        {"baseline": accounting, "contract": contract_accounting},
    )

    authorization = baseline.get("authorization", {})
    next_stage = baseline.get("next_stage", {})
    authorization_pass = (
        authorization.get("instruction") == "进入下一验收点的执行"
        and authorization.get("authorized_through") == "P0/BP0"
        and authorization.get("p1_automatic_progression") is False
        and authorization.get("provider_or_experiment_authorized") is False
        and next_stage.get("stage") == "P1"
        and next_stage.get("gate") == "BP1"
        and next_stage.get("automatic_progression") is False
    )
    add_check(checks, "authorization_boundary", authorization_pass, {"authorization": authorization, "next_stage": next_stage})

    validation = baseline.get("validation_contract", {})
    attempts = baseline.get("validation_attempts", [])
    first_attempt = attempts[0] if len(attempts) == 3 else {}
    second_attempt = attempts[1] if len(attempts) == 3 else {}
    third_attempt = attempts[2] if len(attempts) == 3 else {}
    validation_pass = (
        validation.get("test_file_glob") == "tests/test_benchmark_platform_*.py"
        and validation.get("focused_test") == "tests/test_benchmark_platform_p0.py"
        and validation.get("pytest_basetemp") == "tmp/pytest-benchmark-platform-core"
        and validation.get("commands", [None])[0] == EXPECTED_PLATFORM_TEST_COMMAND
        and first_attempt.get("attempt_id") == "P0-TEST-01"
        and first_attempt.get("status") == "failed_retained"
        and first_attempt.get("exit_code") == 4
        and first_attempt.get("failure_class") == "tooling.powershell_native_glob_not_expanded"
        and second_attempt.get("attempt_id") == "P0-TEST-02"
        and second_attempt.get("status") == "failed_retained"
        and second_attempt.get("exit_code") == 1
        and second_attempt.get("failure_class")
        == "test_scope.protocol_freeze_tests_not_applicable_to_implementation_branch"
        and third_attempt.get("attempt_id") == "P0-TEST-03"
        and third_attempt.get("status") == "rejected_incomplete"
        and third_attempt.get("exit_code") == 0
        and third_attempt.get("failure_class") == "test_scope.keyword_exclusion_dropped_p0_tests"
    )
    add_check(
        checks,
        "validation_command_freeze",
        validation_pass,
        {"active_command": validation.get("commands", [None])[0], "failed_attempts": attempts},
    )

    process_probe = baseline.get("process_probe", {})
    process_capture = process_probe.get("matching_processes_at_capture")
    audit_attempts = baseline.get("audit_attempts", [])
    failed_audit = audit_attempts[0] if len(audit_attempts) == 1 else {}
    live_processes = matching_processes() if probe_processes else []
    process_pass = (
        process_probe.get("command_line_pattern") == PROCESS_COMMAND_PATTERN
        and process_capture == []
        and failed_audit.get("attempt_id") == "P0-AUDIT-01"
        and failed_audit.get("status") == "failed_retained"
        and failed_audit.get("failure_class") == "tooling.process_probe_scope_false_positive"
        and not live_processes
    )
    add_check(
        checks,
        "no_active_platform_processes",
        process_pass,
        {
            "pattern": process_probe.get("command_line_pattern"),
            "capture": process_capture,
            "failed_attempts": audit_attempts,
            "live": live_processes,
            "live_probe_executed": probe_processes,
        },
    )

    failures = [check["check_id"] for check in checks if check["required"] and not check["passed"]]
    return {
        "audit_id": AUDIT_ID,
        "baseline_id": BASELINE_ID,
        "protocol_id": PROTOCOL_ID,
        "generated_at": baseline.get("captured_at"),
        "stage": "P0",
        "gate": "BP0",
        "checks": checks,
        "required_check_count": len(checks),
        "passed_required_check_count": len(checks) - len(failures),
        "required_failures": failures,
        "overall_passed": not failures,
        "stage_status": "complete" if not failures else "blocked_at_p0",
        "accounting": EXPECTED_ACCOUNTING,
        "next_stage": "P1/BP1" if not failures else None,
        "automatic_progression": False,
    }


def hash_entry_map(items: Any) -> tuple[dict[str, str], list[str]]:
    values: dict[str, str] = {}
    duplicates: list[str] = []
    if not isinstance(items, list):
        return values, duplicates
    for item in items:
        if not isinstance(item, dict):
            continue
        path = item.get("path")
        sha256 = item.get("sha256")
        if not isinstance(path, str) or not isinstance(sha256, str):
            continue
        if path in values:
            duplicates.append(path)
        values[path] = sha256
    return values, sorted(set(duplicates))


def requirement_lines(text: str) -> set[str]:
    return {
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def package_import_errors(repo_root: Path) -> list[dict[str, str]]:
    allowed_roots = {
        "__future__",
        "benchmark_platform",
        "collections",
        "enum",
        "hashlib",
        "json",
        "jsonschema",
        "math",
        "pydantic",
        "typing",
    }
    errors: list[dict[str, str]] = []
    for path in sorted((repo_root / "benchmark_platform").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=path.as_posix())
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                root = module.split(".", 1)[0]
                if root not in allowed_roots:
                    errors.append({"path": path.relative_to(repo_root).as_posix(), "module": module})
        if "schemas.benchmark" in source:
            errors.append({"path": path.relative_to(repo_root).as_posix(), "module": "schemas.benchmark"})
    return errors


def audit_p1(repo_root: Path, checkpoint_path: Path, probe_processes: bool = True) -> dict[str, Any]:
    checkpoint = load_json(checkpoint_path)
    checks: list[dict[str, Any]] = []

    identity = {
        "checkpoint_id": checkpoint.get("checkpoint_id"),
        "protocol_id": checkpoint.get("protocol_id"),
        "milestone_id": checkpoint.get("milestone_id"),
        "stage": checkpoint.get("stage"),
        "gate": checkpoint.get("gate"),
        "status": checkpoint.get("status"),
    }
    expected_identity = {
        "checkpoint_id": "fusionagent.benchmark-platform-core.p1-checkpoint.v1",
        "protocol_id": PROTOCOL_ID,
        "milestone_id": "M-BENCH-PLATFORM-CORE-V1",
        "stage": "P1",
        "gate": "BP1",
        "status": "stage_validated_offline",
    }
    add_check(checks, "p1_checkpoint_identity", identity == expected_identity, identity)

    branch = str(git_output(repo_root, "branch", "--show-current")).strip()
    p0_ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor", P0_COMMIT, "HEAD"], cwd=repo_root, check=False
    ).returncode == 0
    git_state = checkpoint.get("git", {})
    git_pass = (
        branch == IMPLEMENTATION_BRANCH
        and git_state.get("branch") == IMPLEMENTATION_BRANCH
        and git_state.get("starting_head") == P0_COMMIT
        and git_state.get("p0_commit") == P0_COMMIT
        and git_state.get("protocol_commit") == PROTOCOL_COMMIT
        and p0_ancestor
    )
    add_check(
        checks,
        "p0_checkpoint_inheritance",
        git_pass,
        {"branch": branch, "p0_is_ancestor": p0_ancestor, "checkpoint": git_state},
    )

    p0_audit_path = repo_root / AUDIT_PATH
    p0_baseline_path = repo_root / BASELINE_PATH
    p0_audit = load_json(p0_audit_path)
    p0_evidence_pass = (
        p0_audit.get("overall_passed") is True
        and p0_audit.get("passed_required_check_count") == 12
        and p0_audit.get("required_check_count") == 12
        and canonical_file_sha256(p0_audit_path) == git_blob_sha256(repo_root, P0_COMMIT, AUDIT_PATH)
        and canonical_file_sha256(p0_baseline_path) == git_blob_sha256(repo_root, P0_COMMIT, BASELINE_PATH)
    )
    add_check(
        checks,
        "p0_evidence_immutable",
        p0_evidence_pass,
        {
            "audit_hash": canonical_file_sha256(p0_audit_path),
            "audit_commit_hash": git_blob_sha256(repo_root, P0_COMMIT, AUDIT_PATH),
            "baseline_hash": canonical_file_sha256(p0_baseline_path),
            "baseline_commit_hash": git_blob_sha256(repo_root, P0_COMMIT, BASELINE_PATH),
        },
    )

    protocol_requirements = str(git_output(repo_root, "show", f"{PROTOCOL_TAG}:requirements.txt"))
    current_requirements = (repo_root / "requirements.txt").read_text(encoding="utf-8")
    base_lines = requirement_lines(protocol_requirements)
    current_lines = requirement_lines(current_requirements)
    added_requirements = sorted(current_lines - base_lines)
    removed_requirements = sorted(base_lines - current_lines)
    dependency_contract = checkpoint.get("dependency_change", {})
    installed_jsonschema = importlib.metadata.version("jsonschema")
    dependency_pass = (
        added_requirements == ["jsonschema>=4.23,<5"]
        and not removed_requirements
        and dependency_contract.get("added") == added_requirements
        and dependency_contract.get("removed") == []
        and dependency_contract.get("installed_version") == installed_jsonschema == "4.23.0"
    )
    add_check(
        checks,
        "p1_dependency_boundary",
        dependency_pass,
        {
            "added": added_requirements,
            "removed": removed_requirements,
            "installed_jsonschema": installed_jsonschema,
        },
    )

    paths = changed_paths(repo_root)
    unexpected_paths = sorted(set(paths) - EXPECTED_P1_FILES)
    missing_paths = sorted(
        path for path in EXPECTED_P1_FILES - {P1_AUDIT_PATH} if not (repo_root / path).is_file()
    )
    add_check(
        checks,
        "p1_change_boundary",
        not unexpected_paths and not missing_paths,
        {"changed_paths": paths, "unexpected": unexpected_paths, "missing": missing_paths},
    )

    package_files = {
        path.relative_to(repo_root).as_posix() for path in (repo_root / "benchmark_platform").glob("*.py")
    }
    expected_package_files = {
        "benchmark_platform/__init__.py",
        "benchmark_platform/canonical.py",
        "benchmark_platform/models.py",
    }
    import_errors = package_import_errors(repo_root)
    package_pass = package_files == expected_package_files and not import_errors
    add_check(
        checks,
        "closed_package_and_import_boundary",
        package_pass,
        {"package_files": sorted(package_files), "import_errors": import_errors},
    )

    file_hashes, duplicate_hash_paths = hash_entry_map(checkpoint.get("files"))
    hash_errors: list[dict[str, str]] = []
    for relative_path, expected_hash in sorted(file_hashes.items()):
        path = repo_root / relative_path
        if not path.is_file():
            hash_errors.append({"path": relative_path, "error": "missing"})
        else:
            actual_hash = canonical_file_sha256(path)
            if actual_hash != expected_hash:
                hash_errors.append(
                    {"path": relative_path, "error": "hash_mismatch", "expected": expected_hash, "actual": actual_hash}
                )
    hashes_pass = set(file_hashes) == P1_HASHED_FILES and not duplicate_hash_paths and not hash_errors
    add_check(
        checks,
        "p1_artifact_hashes",
        hashes_pass,
        {
            "paths": sorted(file_hashes),
            "duplicates": duplicate_hash_paths,
            "errors": hash_errors,
            "missing_manifest_entries": sorted(P1_HASHED_FILES - set(file_hashes)),
            "unexpected_manifest_entries": sorted(set(file_hashes) - P1_HASHED_FILES),
        },
    )

    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    from benchmark_platform.canonical import (
        CANONICALIZATION_ID,
        canonical_json_bytes,
        canonical_sha256,
        derive_seed,
        stable_id,
    )
    from benchmark_platform.models import (
        CanonicalIdentity,
        SeedDerivationInput,
        validate_template_document,
    )

    schema = load_json(repo_root / "docs/current/benchmark/v1/template.schema.json")
    fixture = load_json(repo_root / "tests/fixtures/benchmark_platform/template_contract_valid.json")
    runtime_template = validate_template_document(fixture, schema)
    canonical_identity = CanonicalIdentity(
        design_id="fusionagent.benchmark-design.v1",
        template_family_id="TF-CONTRACT-FIXTURE",
        capability_cell_id="BC-CAUSAL-01",
        partition="development",
        unit_index=0,
        seed=2026081901,
        payload={"task": "road", "priority": 1},
    )
    seed_input = SeedDerivationInput(
        namespace="fusionagent.benchmark.development.v1", master_seed=7, unit_index=0
    )
    actual_contract = {
        "canonicalization_id": CANONICALIZATION_ID,
        "utf8_golden_hex": canonical_json_bytes({"z": [2, 1], "a": "洪水"}).hex(),
        "payload_sha256": canonical_sha256(canonical_identity.payload),
        "stable_id": stable_id(canonical_identity),
        "derived_seed": derive_seed(seed_input),
    }
    schema_contract = checkpoint.get("schema_contract", {})
    runtime_pass = (
        schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
        and schema_contract.get("draft") == "2020-12"
        and schema_contract.get("schema_path") == "docs/current/benchmark/v1/template.schema.json"
        and schema_contract.get("fixture_claim_eligible") is False
        and runtime_template.template_family_id == "TF-CONTRACT-FIXTURE"
        and checkpoint.get("canonical_contract") == actual_contract
    )
    add_check(
        checks,
        "closed_schema_and_canonical_contract",
        runtime_pass,
        {"schema_contract": schema_contract, "actual_canonical_contract": actual_contract},
    )

    accounting = checkpoint.get("accounting", {})
    output_root = Path(str(checkpoint.get("paths", {}).get("future_output_root", "")))
    accounting_pass = (
        accounting == P1_ACCOUNTING
        and output_root.is_absolute()
        and not output_root.exists()
        and not (repo_root / "docs/current/benchmark/platform/v1/implementation/instances.jsonl").exists()
    )
    add_check(
        checks,
        "p1_zero_call_and_no_instance_accounting",
        accounting_pass,
        {"accounting": accounting, "output_root": str(output_root), "output_root_exists": output_root.exists()},
    )

    validation = checkpoint.get("validation", {})
    next_stage = checkpoint.get("next_stage", {})
    validation_attempts = validation.get("failed_attempts", [])
    failed_core = validation_attempts[0] if len(validation_attempts) == 1 else {}
    validation_pass = (
        validation.get("core_test_command") == EXPECTED_PLATFORM_TEST_COMMAND
        and validation.get("focused_test_files")
        == [
            "tests/test_benchmark_platform_models.py",
            "tests/test_benchmark_platform_canonical.py",
            "tests/test_benchmark_platform_p1_audit.py",
        ]
        and validation.get("focused_tests_passed") == 23
        and validation.get("core_tests_passed") == 32
        and failed_core.get("attempt_id") == "P1-CORE-01"
        and failed_core.get("status") == "failed_retained"
        and failed_core.get("failure_class")
        == "test_scope.p0_dependency_snapshot_compared_to_p1_worktree"
        and next_stage.get("stage") == "P2"
        and next_stage.get("gate") == "BP2"
        and next_stage.get("automatic_progression") is False
    )
    add_check(
        checks,
        "p1_validation_and_next_gate",
        validation_pass,
        {"validation": validation, "next_stage": next_stage},
    )

    live_processes = matching_processes() if probe_processes else []
    add_check(
        checks,
        "no_active_platform_processes",
        not live_processes,
        {"live": live_processes, "live_probe_executed": probe_processes},
    )

    failures = [check["check_id"] for check in checks if check["required"] and not check["passed"]]
    return {
        "audit_id": AUDIT_ID,
        "checkpoint_id": expected_identity["checkpoint_id"],
        "protocol_id": PROTOCOL_ID,
        "generated_at": checkpoint.get("captured_at"),
        "stage": "P1",
        "gate": "BP1",
        "checks": checks,
        "required_check_count": len(checks),
        "passed_required_check_count": len(checks) - len(failures),
        "required_failures": failures,
        "overall_passed": not failures,
        "stage_status": "complete" if not failures else "blocked_at_p1",
        "accounting": P1_ACCOUNTING,
        "next_stage": "P2/BP2" if not failures else None,
        "automatic_progression": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a bounded FusionAgent benchmark platform core stage.")
    parser.add_argument("--stage", choices=["P0", "P1"], required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    baseline_path = args.baseline if args.baseline.is_absolute() else repo_root / args.baseline
    output_path = args.output if args.output.is_absolute() else repo_root / args.output
    if args.stage == "P0":
        result = audit_p0(repo_root.resolve(), baseline_path.resolve())
    else:
        result = audit_p1(repo_root.resolve(), baseline_path.resolve())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"overall_passed": result["overall_passed"], "required_failures": result["required_failures"]}))
    return 0 if result["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
