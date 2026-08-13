from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.inmemory_repository import InMemoryKGRepository
from schemas.research_case_manifest import load_research_case_manifest
from services.research_baselines import (
    DETERMINISTIC_OUTPUT_PROTOCOL_ID,
    BaselineGroup,
    CanonicalContextFactory,
    DeterministicBaselineRunner,
)
from services.research_plan_evaluation import EVALUATOR_ID, evaluate_research_plan


GROUPS = (BaselineGroup.fixed_workflow, BaselineGroup.rules_only, BaselineGroup.kg_only)


def run_deterministic_formal(manifest_path: Path) -> dict[str, Any]:
    manifest = load_research_case_manifest(manifest_path)
    repository = InMemoryKGRepository(experience_policy="pinned_snapshot")
    factory = CanonicalContextFactory(repository)
    runner = DeterministicBaselineRunner()
    rows = []
    for case in manifest.cases:
        context = factory.build(case)
        for group in GROUPS:
            projection = factory.project(context, group)
            plan = runner.run_planning_decision(projection)
            allowed_strings = set(_strings(projection.payload))
            evaluation = evaluate_research_plan(case, plan, allowed_strings=allowed_strings)
            rows.append(
                {
                    "run_id": f"formal-{case.case_id.lower()}-{group.value}-r1",
                    "case_id": case.case_id,
                    "group": group.value,
                    "input_hash": projection.input_hash,
                    "allowed_top_level_fields": projection.allowed_top_level_fields,
                    "forbidden_top_level_fields": projection.forbidden_top_level_fields,
                    "plan": plan.model_dump(mode="json"),
                    "output_hash": _semantic_hash(plan.model_dump(mode="json")),
                    "evaluation": evaluation.model_dump(mode="json"),
                }
            )
    return {
        "report_type": "planning_only_deterministic_formal",
        "protocol_id": DETERMINISTIC_OUTPUT_PROTOCOL_ID,
        "protocol_status": "post_llm_formal_deterministic_contract_freeze",
        "implementation_commit": _git_head(),
        "implementation_dirty": _git_dirty(),
        "implementation_hashes": {
            "services/research_baselines.py": _file_hash(REPO_ROOT / "services/research_baselines.py"),
            "services/research_plan_evaluation.py": _file_hash(
                REPO_ROOT / "services/research_plan_evaluation.py"
            ),
            "schemas/research_llm_pilot.py": _file_hash(
                REPO_ROOT / "schemas/research_llm_pilot.py"
            ),
            "scripts/run_research_deterministic_formal.py": _file_hash(Path(__file__)),
        },
        "manifest_id": manifest.manifest_id,
        "manifest_version": manifest.manifest_version,
        "manifest_sha256": _file_hash(manifest_path),
        "kg_identity": repository.get_knowledge_identity(),
        "evaluator_id": EVALUATOR_ID,
        "groups": [group.value for group in GROUPS],
        "run_count": len(rows),
        "negative_control_case_ids": list(manifest.negative_control_case_ids),
        "claim_boundary": (
            "This deterministic contract was frozen after the LLM formal batch to repair a pre-existing common-output "
            "contract gap. It does not alter or rerun LLM outputs and must be disclosed in comparisons."
        ),
        "runs": rows,
    }


def _strings(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _semantic_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()


def _git_dirty() -> bool:
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=REPO_ROOT,
        text=True,
    )
    return bool(status.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the three deterministic planning baselines.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "docs/current/research-case-manifest-v1.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"Refusing to overwrite deterministic formal evidence: {args.output}")
    report = run_deterministic_formal(args.manifest)
    if report["implementation_dirty"]:
        raise RuntimeError("Deterministic formal execution requires a clean worktree.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
