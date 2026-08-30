from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/current/benchmark/v1"
FIXTURE = ROOT / "tests/fixtures/benchmark_platform/template_contract_valid.json"
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


def cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    effective_env = os.environ.copy()
    effective_env["PYTHONPATH"] = str(ROOT)
    effective_env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    if env:
        effective_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "benchmark_platform.cli", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=effective_env,
        check=False,
        timeout=30,
    )


def template_path(tmp_path: Path) -> Path:
    template = json.loads(FIXTURE.read_text(encoding="utf-8"))
    template["template_family_id"] = "TF-PLAN-STRUCTURE-INVALID"
    template["capability_cell_ids"] = ["BC-DIAG-03"]
    template["crosswalk"]["references"][0]["reference_id"] = "contract.road.fused.v1"
    template["task_state"]["tasks"][0]["contract_ids"] = ["contract.road.fused.v1"]
    template["generation"]["seed_namespace"] = "fusionagent-benchmark-v1-development"
    template["generation"]["instance_id_pattern"] = "^BDV1-DEV-BC-[A-Z0-9-]+-[0-9]{3}$"
    path = tmp_path / "template.json"
    path.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def common(template: Path, run_root: Path) -> list[str]:
    return [
        "--design-root", str(DESIGN),
        "--repo-root", str(ROOT),
        "--template", str(template),
        "--run-root", str(run_root),
        "--code-revision", "p6-contract-test",
    ]


def generated_run(tmp_path: Path) -> tuple[Path, Path]:
    template = template_path(tmp_path)
    run_root = tmp_path / "run"
    result = cli(
        "generate-development",
        "--design-root", str(DESIGN),
        "--repo-root", str(ROOT),
        "--template", str(template),
        "--output-root", str(run_root),
        "--run-id", "BDV1-DEV-P6-CLI",
        "--capability-cell-id", "BC-DIAG-03",
        "--unit-index", "0",
        "--code-revision", "p6-contract-test",
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["stage"] == "generated"
    return template, run_root


def test_help_exposes_exact_bounded_command_set() -> None:
    result = cli("--help")
    assert result.returncode == 0
    command_line = next(line for line in result.stdout.splitlines() if "validate-design," in line)
    exposed = set(command_line.strip().strip("{}").split(","))
    assert exposed == ALLOWED_COMMANDS
    lowered = result.stdout.lower()
    assert all(token not in lowered for token in FORBIDDEN_TOKENS)


def test_structured_exit_codes_for_success_usage_and_validation(tmp_path: Path) -> None:
    success = cli("validate-design", "--design-root", str(DESIGN), "--repo-root", str(ROOT))
    assert success.returncode == 0
    assert json.loads(success.stdout) == {
        "cell_count": 17,
        "command": "validate-design",
        "design_id": "fusionagent.benchmark-design.v1",
        "status": "ok",
    }
    assert success.stderr == ""

    usage = cli("unknown-command")
    assert usage.returncode == 2
    assert json.loads(usage.stderr)["error_class"] == "usage"
    assert usage.stdout == ""

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{}\n", encoding="utf-8")
    validation = cli(
        "validate-template",
        "--design-root", str(DESIGN),
        "--repo-root", str(ROOT),
        "--template", str(invalid),
    )
    assert validation.returncode == 3
    assert json.loads(validation.stderr)["error_class"] == "validation"
    assert validation.stdout == ""


def test_full_development_lifecycle_is_explicit_and_temporary(tmp_path: Path) -> None:
    template, run_root = generated_run(tmp_path)
    resume = cli("resume-development", *common(template, run_root), "--expected-stage", "generated")
    assert resume.returncode == 0, resume.stderr
    assert json.loads(resume.stdout)["stage"] == "generated"

    validated = cli("validate-run", *common(template, run_root))
    assert validated.returncode == 0, validated.stderr
    assert json.loads(validated.stdout)["stage"] == "relations_validated"

    projected = cli("project-views", *common(template, run_root))
    assert projected.returncode == 0, projected.stderr
    assert json.loads(projected.stdout)["stage"] == "views_projected"

    audited = cli("audit-run", *common(template, run_root))
    assert audited.returncode == 0, audited.stderr
    payload = json.loads(audited.stdout)
    assert payload["stage"] == "development_complete"
    assert payload["terminal_binding"]["covered_file_count"] >= 10
    assert (run_root / "checksums.json").is_file()
    checkpoint = json.loads((run_root / "checkpoint.json").read_text(encoding="utf-8"))
    assert checkpoint["terminal_status"] == "development_complete"
    assert not Path(r"D:\code\fusionagent-evidence\benchmark-platform\development-v1").exists()


def test_existing_root_and_tampered_resume_fail_closed(tmp_path: Path) -> None:
    template, run_root = generated_run(tmp_path)
    duplicate = cli(
        "generate-development",
        "--design-root", str(DESIGN),
        "--repo-root", str(ROOT),
        "--template", str(template),
        "--output-root", str(run_root),
        "--run-id", "BDV1-DEV-P6-CLI",
        "--capability-cell-id", "BC-DIAG-03",
        "--unit-index", "0",
        "--code-revision", "p6-contract-test",
    )
    assert duplicate.returncode == 3
    assert json.loads(duplicate.stderr)["error_class"] == "validation"

    (run_root / "instances.jsonl").write_text("{\"tampered\":true}\n", encoding="utf-8")
    resumed = cli("resume-development", *common(template, run_root), "--expected-stage", "generated")
    assert resumed.returncode == 3
    assert json.loads(resumed.stderr)["error_class"] == "validation"


def test_cli_operates_with_socket_disabled(tmp_path: Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.mkdir()
    (blocker / "sitecustomize.py").write_text(
        "import socket\n"
        "def blocked(*args, **kwargs):\n"
        "    raise RuntimeError('network disabled by BP6 test')\n"
        "socket.socket.connect = blocked\n"
        "socket.socket.connect_ex = blocked\n"
        "socket.create_connection = blocked\n",
        encoding="utf-8",
    )
    env = {"PYTHONPATH": os.pathsep.join([str(blocker), str(ROOT)])}
    result = cli("validate-design", "--design-root", str(DESIGN), "--repo-root", str(ROOT), env=env)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["status"] == "ok"


def test_cli_has_no_forbidden_runtime_imports() -> None:
    source = (ROOT / "benchmark_platform/cli.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {"requests", "httpx", "urllib", "socket", "openai", "anthropic", "neo4j", "llm", "celery", "redis"}
    hits: list[str] = []
    for node in ast.walk(tree):
        modules = [alias.name for alias in node.names] if isinstance(node, ast.Import) else ([node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
        hits.extend(module for module in modules if module.split(".", 1)[0] in forbidden)
    assert hits == []
