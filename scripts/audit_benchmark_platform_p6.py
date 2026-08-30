from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark_platform.cli import EXIT_INTERNAL, EXIT_OK, EXIT_USAGE, EXIT_VALIDATION, build_parser


AUDIT_ID = "fusionagent.benchmark-platform-core.p6-audit.v1"
CHECKPOINT_ID = "fusionagent.benchmark-platform-core.p6-checkpoint.v1"
ALLOWED_COMMANDS = {
    "validate-design",
    "validate-template",
    "generate-development",
    "validate-run",
    "project-views",
    "audit-run",
    "resume-development",
}
FORBIDDEN_TOKENS = {"confirmation", "e2e", "judge", "provider", "model", "execute"}
FORBIDDEN_IMPORTS = {"requests", "httpx", "urllib", "socket", "openai", "anthropic", "neo4j", "llm", "celery", "redis"}
ACCOUNTING = {"benchmark_instances_generated": 0, "provider_calls": 0, "judge_calls": 0, "formal_result_roots_created": 0, "confirmation_unsealed": False, "selective_e2e_selected": False, "platform_implementation_started": True}


def file_hash(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _commands() -> set[str]:
    parser = build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def _import_hits(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.as_posix())
    hits: list[str] = []
    for node in ast.walk(tree):
        modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
        hits.extend(module for module in modules if module.split(".", 1)[0] in FORBIDDEN_IMPORTS)
    return hits


def _subprocess_boundary(repo_root: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="benchmark-platform-p6-audit-") as directory:
        blocker = Path(directory)
        (blocker / "sitecustomize.py").write_text(
            "import socket\n"
            "def blocked(*args, **kwargs):\n"
            "    raise RuntimeError('network disabled by BP6 audit')\n"
            "socket.socket.connect = blocked\n"
            "socket.socket.connect_ex = blocked\n"
            "socket.create_connection = blocked\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = os.pathsep.join([str(blocker), str(repo_root)])
        validate = subprocess.run(
            [
                sys.executable,
                "-m",
                "benchmark_platform.cli",
                "validate-design",
                "--design-root",
                str(repo_root / "docs/current/benchmark/v1"),
                "--repo-root",
                str(repo_root),
            ],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
            timeout=30,
        )
        usage = subprocess.run(
            [sys.executable, "-m", "benchmark_platform.cli", "unknown-command"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            check=False,
            timeout=30,
        )
        try:
            validate_payload = json.loads(validate.stdout)
            usage_payload = json.loads(usage.stderr)
        except json.JSONDecodeError:
            validate_payload = {}
            usage_payload = {}
        return {
            "validate_exit_code": validate.returncode,
            "validate_status": validate_payload.get("status"),
            "validate_stderr": validate.stderr,
            "usage_exit_code": usage.returncode,
            "usage_error_class": usage_payload.get("error_class"),
            "usage_stdout": usage.stdout,
        }


def audit_p6(repo_root: Path, checkpoint_path: Path) -> dict[str, Any]:
    checkpoint = load(checkpoint_path)
    checks: list[dict[str, Any]] = []

    def check(check_id: str, passed: bool, details: Any) -> None:
        checks.append({"check_id": check_id, "required": True, "passed": bool(passed), "details": details})

    identity = {key: checkpoint.get(key) for key in ("checkpoint_id", "protocol_id", "stage", "gate", "status")}
    check("p6_checkpoint_identity", identity == {"checkpoint_id": CHECKPOINT_ID, "protocol_id": "fusionagent.benchmark-platform-implementation-protocol.v1", "stage": "P6", "gate": "BP6", "status": "stage_validated_offline"}, identity)

    commands = _commands()
    help_text = build_parser().format_help().lower()
    forbidden_help = sorted(token for token in FORBIDDEN_TOKENS if token in help_text)
    check("bounded_cli_surface", commands == ALLOWED_COMMANDS and not forbidden_help, {"commands": sorted(commands), "forbidden_help_tokens": forbidden_help})

    exit_codes = {"ok": EXIT_OK, "usage": EXIT_USAGE, "validation": EXIT_VALIDATION, "internal": EXIT_INTERNAL}
    check("stable_exit_code_contract", exit_codes == {"ok": 0, "usage": 2, "validation": 3, "internal": 4}, exit_codes)

    import_hits = _import_hits(repo_root / "benchmark_platform/cli.py")
    check("offline_import_boundary", not import_hits, {"forbidden_imports": import_hits})

    try:
        subprocess_details = _subprocess_boundary(repo_root)
        subprocess_passed = subprocess_details == {"validate_exit_code": 0, "validate_status": "ok", "validate_stderr": "", "usage_exit_code": 2, "usage_error_class": "usage", "usage_stdout": ""}
    except Exception as error:
        subprocess_details = {"error": f"{type(error).__name__}: {error}"}
        subprocess_passed = False
    check("no_network_and_structured_subprocess", subprocess_passed, subprocess_details)

    errors: list[str] = []
    for item in checkpoint.get("files", []):
        path = repo_root / str(item.get("path", ""))
        if not path.is_file() or file_hash(path) != item.get("sha256"):
            errors.append(str(item.get("path")))
    check("p6_artifact_hashes", not errors and bool(checkpoint.get("files")), {"errors": errors, "count": len(checkpoint.get("files", []))})

    future_root = Path(checkpoint["paths"]["future_output_root"])
    check("zero_calls_and_no_future_output_root", checkpoint.get("accounting") == ACCOUNTING and not future_root.exists(), {"accounting": checkpoint.get("accounting"), "future_output_root": str(future_root), "exists": future_root.exists()})
    check("next_gate_boundary", checkpoint.get("next_stage") == {"stage": "P7", "gate": "BP7", "automatic_progression": False}, checkpoint.get("next_stage"))

    failures = [item["check_id"] for item in checks if item["required"] and not item["passed"]]
    return {"audit_id": AUDIT_ID, "checkpoint_id": CHECKPOINT_ID, "protocol_id": "fusionagent.benchmark-platform-implementation-protocol.v1", "stage": "P6", "gate": "BP6", "checks": checks, "required_check_count": len(checks), "passed_required_check_count": len(checks) - len(failures), "required_failures": failures, "overall_passed": not failures, "stage_status": "complete" if not failures else "blocked_at_p6", "accounting": ACCOUNTING, "next_stage": "P7/BP7" if not failures else None, "automatic_progression": False}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit the bounded benchmark platform P6 stage.")
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    checkpoint = args.checkpoint if args.checkpoint.is_absolute() else root / args.checkpoint
    output = args.output if args.output.is_absolute() else root / args.output
    result = audit_p6(root, checkpoint)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"overall_passed": result["overall_passed"], "required_failures": result["required_failures"]}))
    return 0 if result["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
