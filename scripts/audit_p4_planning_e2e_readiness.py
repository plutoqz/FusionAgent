from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.tooling import build_default_tool_registry
from kg.inmemory_repository import InMemoryKGRepository
from schemas.research_case_manifest import load_research_case_manifest
from schemas.research_llm_pilot import ResearchPlanningDecision
from services.research_plan_runtime_adapter import ResearchPlanRuntimeAdapter


P4_CASES = {"C02", "C04", "C06"}


def audit_p4_readiness(
    *,
    llm_path: Path,
    deterministic_path: Path,
    manifest_path: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    llm = _read_llm_runs(llm_path)
    deterministic = _read_json(deterministic_path)
    manifest = load_research_case_manifest(manifest_path)
    cases = {case.case_id: case for case in manifest.cases if case.case_id in P4_CASES}
    repository = InMemoryKGRepository(experience_policy="pinned_snapshot")
    tool_registry = build_default_tool_registry()
    adapter = ResearchPlanRuntimeAdapter(repository, tool_registry=tool_registry)
    rows = []
    for run in llm["runs"]:
        if run["case_id"] in P4_CASES:
            rows.append(
                _audit_run(
                    case=cases[run["case_id"]],
                    condition=run["knowledge_condition"],
                    plan=run.get("plan") or {},
                    source="llm",
                    adapter=adapter,
                )
            )
    for run in deterministic["runs"]:
        if run["case_id"] in P4_CASES:
            rows.append(
                _audit_run(
                    case=cases[run["case_id"]],
                    condition=run["group"],
                    plan=run["plan"],
                    source="deterministic",
                    adapter=adapter,
                )
            )
    return {
        "report_type": "p4_planning_e2e_readiness",
        "case_ids": sorted(P4_CASES),
        "expected_run_count": 18,
        "audited_run_count": len(rows),
        "ready_run_count": sum(row["ready"] for row in rows),
        "ready": len(rows) == 18 and all(row["ready"] for row in rows),
        "blocker_counts": _blocker_counts(rows),
        "required_adapter_contract": {
            "stages": ["selected", "resolved", "executed", "evaluated"],
            "selected_fields": ["task_kind", "source_ids", "algorithm_id", "delivery_state"],
            "resolved_fields": ["effective_source_id", "component_source_ids", "effective_algorithm_id", "contract_id"],
            "executed_fields": ["handler_name", "artifact_path", "artifact_sha256", "runtime_status"],
            "evaluated_fields": ["raw_quality_result", "adapted_quality_result", "contract_state", "gap_declaration"],
        },
        "claim_boundary": (
            "This audit verifies wiring readiness only. It does not materialize external data, execute fusion, "
            "or establish end-to-end capability. No run may be omitted because it is inconvenient."
        ),
        "runs": sorted(rows, key=lambda row: (row["case_id"], row["condition"])),
    }


def _audit_run(
    *,
    case: Any,
    condition: str,
    plan: dict[str, Any],
    source: str,
    adapter: ResearchPlanRuntimeAdapter,
) -> dict[str, Any]:
    try:
        decision = ResearchPlanningDecision.model_validate(plan)
    except ValueError as exc:
        return {
            "case_id": case.case_id,
            "condition": condition,
            "source": source,
            "decision": plan.get("decision"),
            "contract_ids": list(case.request_scope.contract_ids),
            "resolution": None,
            "blockers": ["invalid_research_planning_decision"],
            "validation_error": str(exc),
            "ready": False,
        }

    resolution = adapter.resolve(case=case, condition=condition, decision=decision)
    blockers = sorted(
        {
            reason.lower()
            for item in resolution.task_resolutions
            if item.resolution_status == "rejected"
            for reason in item.reason_codes
        }
        | {reason.lower() for reason in resolution.resolved.get("reason_codes", [])}
    )
    if resolution.workflow_plan is None:
        blockers.append("no_executable_workflow_plan")
    unique_blockers = sorted(set(blockers))
    return {
        "case_id": case.case_id,
        "condition": condition,
        "source": source,
        "decision": plan.get("decision"),
        "contract_ids": list(case.request_scope.contract_ids),
        "resolution": resolution.model_dump(mode="json"),
        "blockers": unique_blockers,
        "ready": not unique_blockers,
    }


def _blocker_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    blockers = sorted({blocker for row in rows for blocker in row["blockers"]})
    return {blocker: sum(blocker in row["blockers"] for row in rows) for blocker in blockers}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_llm_runs(path: Path) -> dict[str, list[dict[str, Any]]]:
    if path.is_file():
        return _read_json(path)
    result_paths = sorted(path.glob("runs/*/result.json"))
    if not result_paths:
        raise ValueError(f"No formal result.json files found under {path}")
    schedule = _read_json(path / "schedule.json")
    schedule_by_run = {item["run_id"]: item for item in schedule["items"]}
    if len(schedule_by_run) != len(schedule["items"]):
        raise ValueError("Formal schedule contains duplicate run_id values")
    results = [_read_json(result_path) for result_path in result_paths]
    result_by_run = {item.get("run_id"): item for item in results}
    if None in result_by_run or len(result_by_run) != len(results):
        raise ValueError("Formal results contain missing or duplicate run_id values")
    if set(schedule_by_run) != set(result_by_run):
        raise ValueError("Formal schedule and result run_id sets do not match")
    runs = []
    for run_id, result in result_by_run.items():
        scheduled = schedule_by_run[run_id]
        runs.append(
            {
                **result,
                "case_id": scheduled["case_id"],
                "knowledge_condition": scheduled["knowledge_condition"],
            }
        )
    return {"runs": runs}


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit P4 planning-to-runtime readiness without execution.")
    parser.add_argument("--llm", type=Path, required=True)
    parser.add_argument("--deterministic", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=REPO_ROOT / "docs/current/research-case-manifest-v1.json",
    )
    parser.add_argument("--cache-dir", type=Path, required=True)
    args = parser.parse_args()
    report = audit_p4_readiness(
        llm_path=args.llm,
        deterministic_path=args.deterministic,
        manifest_path=args.manifest,
        cache_dir=args.cache_dir,
    )
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if report["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
