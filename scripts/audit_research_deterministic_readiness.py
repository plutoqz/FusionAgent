from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.inmemory_repository import InMemoryKGRepository
from schemas.research_case_manifest import load_research_case_manifest
from schemas.research_llm_pilot import ResearchPlanningDecision
from services.research_baselines import BaselineGroup, CanonicalContextFactory, DeterministicBaselineRunner


DETERMINISTIC_GROUPS = (
    BaselineGroup.fixed_workflow,
    BaselineGroup.rules_only,
    BaselineGroup.kg_only,
)


def audit_deterministic_readiness(manifest_path: Path) -> dict[str, Any]:
    manifest = load_research_case_manifest(manifest_path)
    repository = InMemoryKGRepository(experience_policy="pinned_snapshot")
    factory = CanonicalContextFactory(repository)
    runner = DeterministicBaselineRunner()
    records = []
    for case in manifest.cases:
        context = factory.build(case)
        for group in DETERMINISTIC_GROUPS:
            projection = factory.project(context, group)
            raw_output = runner.run_planning_decision(projection).model_dump(mode="json")
            schema_error = None
            try:
                ResearchPlanningDecision.model_validate(raw_output)
            except ValidationError as exc:
                schema_error = exc.errors(include_url=False)
            records.append(
                {
                    "case_id": case.case_id,
                    "group": group.value,
                    "input_hash": projection.input_hash,
                    "raw_output": raw_output,
                    "output_hash": _semantic_hash(raw_output),
                    "research_planning_decision_valid": schema_error is None,
                    "schema_error": schema_error,
                }
            )
    valid = sum(record["research_planning_decision_valid"] for record in records)
    return {
        "report_type": "deterministic_planning_comparison_readiness",
        "manifest_id": manifest.manifest_id,
        "manifest_version": manifest.manifest_version,
        "kg_identity": repository.get_knowledge_identity(),
        "groups": [group.value for group in DETERMINISTIC_GROUPS],
        "case_count": len(manifest.cases),
        "run_count": len(records),
        "shared_schema_valid_count": valid,
        "shared_schema_invalid_count": len(records) - valid,
        "comparison_ready": valid == len(records),
        "blockers": (
            []
            if valid == len(records)
            else [
                "deterministic_outputs_do_not_conform_to_frozen_research_planning_decision",
                "six_group_common_evaluator_contract_not_satisfied",
            ]
        ),
        "claim_boundary": (
            "All six groups may share the evaluator only when comparison_ready=true. Readiness does not establish "
            "fairness, superiority, statistical significance, or completion of manual review."
        ),
        "records": records,
    }


def _semantic_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit deterministic groups for six-group comparison readiness.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "docs/current/research-case-manifest-v1.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_deterministic_readiness(args.manifest)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if report["comparison_ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
