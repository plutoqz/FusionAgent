from __future__ import annotations

import argparse
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a bounded FusionAgent benchmark platform core stage.")
    parser.add_argument("--stage", choices=["P0"], required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    baseline_path = args.baseline if args.baseline.is_absolute() else repo_root / args.baseline
    output_path = args.output if args.output.is_absolute() else repo_root / args.output
    result = audit_p0(repo_root.resolve(), baseline_path.resolve())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"overall_passed": result["overall_passed"], "required_failures": result["required_failures"]}))
    return 0 if result["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
