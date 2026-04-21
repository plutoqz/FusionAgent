from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_REQUIRED_FILES = [
    REPO_ROOT / "docs/superpowers/specs/2026-04-21-no-ui-maturity-target.md",
    REPO_ROOT / "docs/superpowers/specs/2026-04-21-no-ui-maturity-gap-ledger.md",
    REPO_ROOT / "docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json",
    REPO_ROOT / "docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json",
    REPO_ROOT / "docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md",
    REPO_ROOT / "docs/superpowers/specs/2026-04-21-scenario-eval-manifest.json",
    REPO_ROOT / "docs/superpowers/specs/2026-04-21-scenario-regression-set-design.md",
    REPO_ROOT / "docs/superpowers/specs/2026-04-21-scenario-trigger-proof.md",
    REPO_ROOT / "docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.json",
    REPO_ROOT / "docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md",
    REPO_ROOT / "docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.json",
    REPO_ROOT / "docs/superpowers/specs/2026-04-21-no-ui-maturity-evidence-freeze.md",
    REPO_ROOT / "docs/superpowers/specs/2026-04-21-operator-read-model-contract.md",
    REPO_ROOT / "docs/no-ui-agent-operations.md",
]

README_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "README.en.md",
]

STALE_README_PHRASES = [
    "prototype only",
    "only a prototype",
    "just a prototype",
    "仅原型",
    "只是原型",
    "仅仅是原型",
]

STALE_README_CONTEXT_PATTERNS = [
    ("agent prototype opening", ["agent prototype"]),
    ("agent prototype opening", ["智能体原型"]),
]

README_MATURITY_MARKERS = [
    "无界面的成熟矢量数据融合智能体：已达到",
    "FusionAgent 当前可以作为无界面的成熟矢量数据融合智能体运行",
    "Mature no-UI vector data fusion agent: reached",
    "No-UI mature vector data fusion agent: achieved",
    "FusionAgent can now run as a mature no-UI vector data fusion agent",
]


def collect_static_maturity_status(required_files: list[Path]) -> dict[str, Any]:
    return {"required_files": {str(path): path.exists() for path in required_files}}


def collect_readme_stale_wording_status(readme_files: list[Path]) -> dict[str, Any]:
    matches: dict[str, list[str]] = {}
    marker_matches: dict[str, list[str]] = {}
    missing_files: list[str] = []
    for path in readme_files:
        if not path.exists():
            matches[str(path)] = ["missing"]
            marker_matches[str(path)] = []
            missing_files.append(str(path))
            continue
        text = path.read_text(encoding="utf-8")
        normalized_text = text.lower()
        found = [
            phrase
            for phrase in STALE_README_PHRASES
            if phrase.lower() in normalized_text
        ]
        for label, patterns in STALE_README_CONTEXT_PATTERNS:
            if any(pattern.lower() in normalized_text for pattern in patterns):
                found.append(label)
        markers = [
            marker
            for marker in README_MATURITY_MARKERS
            if marker.lower() in normalized_text
        ]
        matches[str(path)] = found
        marker_matches[str(path)] = markers

    has_maturity_markers = any(marker_matches.values())
    stale_wording_found = any(matches.values())
    readme_wording_passed = (
        not missing_files and (not has_maturity_markers or not stale_wording_found)
    )
    return {
        "stale_readme_phrases": matches,
        "readme_maturity_markers": marker_matches,
        "readme_repositioning_status": (
            "enforced" if has_maturity_markers else "pending"
        ),
        "readme_repositioning_complete": has_maturity_markers,
        "readme_wording_passed": readme_wording_passed,
    }


def run_pytest() -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", "-q"]
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "command": "python -m pytest -q",
        "returncode": result.returncode,
        "passed": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def build_summary(
    *, run_tests: bool, require_readme_repositioning: bool = False
) -> dict[str, Any]:
    static_status = collect_static_maturity_status(DEFAULT_REQUIRED_FILES)
    readme_status = collect_readme_stale_wording_status(README_FILES)
    tests_status = run_pytest() if run_tests else {"skipped": True}

    required_files_passed = all(static_status["required_files"].values())
    readme_wording_passed = readme_status["readme_wording_passed"]
    readme_repositioning_complete = readme_status["readme_repositioning_complete"]
    tests_passed = tests_status.get("passed", True) if run_tests else True
    static_check_passed = required_files_passed and readme_wording_passed
    maturity_gate_passed = static_check_passed and readme_repositioning_complete
    passed = static_check_passed and tests_passed and (
        readme_repositioning_complete if require_readme_repositioning else True
    )

    return {
        "passed": passed,
        "static_check_passed": static_check_passed,
        "maturity_gate_passed": maturity_gate_passed,
        "readme_repositioning_required": require_readme_repositioning,
        "static": {
            **static_status,
            **readme_status,
            "required_files_passed": required_files_passed,
            "readme_wording_passed": readme_wording_passed,
            "readme_repositioning_complete": readme_repositioning_complete,
        },
        "tests": tests_status,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run static checks for the no-UI maturity gate."
    )
    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Also run python -m pytest -q.",
    )
    parser.add_argument(
        "--require-readme-repositioning",
        action="store_true",
        help="Fail unless README maturity markers are present and stale prototype-only wording is absent.",
    )
    args = parser.parse_args()

    summary = build_summary(
        run_tests=args.run_tests,
        require_readme_repositioning=args.require_readme_repositioning,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
