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
from scripts.freeze_research_repeated_protocol import verify_repeated_freeze
from scripts.run_research_llm_repeated_formal import assert_frozen_source_state
from services.research_baselines import BaselineGroup, CanonicalContextFactory, DeterministicBaselineRunner
from services.research_plan_evaluation import EVALUATOR_ID, evaluate_research_plan


GROUPS = (BaselineGroup.fixed_workflow, BaselineGroup.rules_only, BaselineGroup.kg_only)


def run_deterministic_repeated(freeze_root: Path, manifest_path: Path) -> dict[str, Any]:
    audit = verify_repeated_freeze(freeze_root)
    if not audit["passed"]:
        raise RuntimeError(f"Repeated formal freeze audit failed: {audit['blockers']}")
    protocol = _read_json(freeze_root / "formal_protocol.json")
    assert_frozen_source_state(protocol)
    manifest = load_research_case_manifest(manifest_path)
    repository = InMemoryKGRepository(experience_policy="pinned_snapshot")
    factory = CanonicalContextFactory(repository)
    runner = DeterministicBaselineRunner()
    rows = []
    repetitions = protocol["design"]["deterministic_repetitions"]
    for case in manifest.cases:
        context = factory.build(case)
        for group in GROUPS:
            projection = factory.project(context, group)
            for replicate in range(1, repetitions + 1):
                plan = runner.run_planning_decision(projection)
                plan_payload = plan.model_dump(mode="json")
                evaluation = evaluate_research_plan(
                    case,
                    plan,
                    allowed_strings=set(_strings(projection.payload)),
                )
                rows.append(
                    {
                        "run_id": f"formal-v2-{case.case_id.lower()}-{group.value}-r{replicate}",
                        "case_id": case.case_id,
                        "group": group.value,
                        "replicate": replicate,
                        "input_hash": projection.input_hash,
                        "plan": plan_payload,
                        "output_hash": _semantic_hash(plan_payload),
                        "evaluation": evaluation.model_dump(mode="json"),
                    }
                )
    return {
        "report_type": "planning_only_deterministic_repeated_formal",
        "protocol_id": protocol["protocol_id"],
        "implementation_commit": protocol["implementation_commit"],
        "execution_commit": _git_head(),
        "manifest_sha256": _file_hash(manifest_path),
        "kg_identity": repository.get_knowledge_identity(),
        "evaluator_id": EVALUATOR_ID,
        "groups": [group.value for group in GROUPS],
        "repetitions": repetitions,
        "run_count": len(rows),
        "negative_control_case_ids": list(manifest.negative_control_case_ids),
        "claim_boundary": (
            "Repeated deterministic rows verify exact stability under the shared v2 implementation; "
            "they are not independent stochastic samples."
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


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_head() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run repeated deterministic planning baselines.")
    parser.add_argument("--freeze-root", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "docs/current/research-case-manifest-v1.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"Refusing to overwrite repeated deterministic evidence: {args.output}")
    report = run_deterministic_repeated(args.freeze_root, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
