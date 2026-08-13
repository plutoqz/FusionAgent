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
from services.source_asset_service import SourceAssetService


P4_CASES = {"C02", "C04", "C06"}


def audit_p4_readiness(
    *,
    llm_path: Path,
    deterministic_path: Path,
    manifest_path: Path,
    cache_dir: Path,
) -> dict[str, Any]:
    llm = _read_json(llm_path)
    deterministic = _read_json(deterministic_path)
    manifest = load_research_case_manifest(manifest_path)
    cases = {case.case_id: case for case in manifest.cases if case.case_id in P4_CASES}
    repository = InMemoryKGRepository(experience_policy="pinned_snapshot")
    tool_registry = build_default_tool_registry()
    source_service = SourceAssetService(repo_root=REPO_ROOT, cache_dir=cache_dir)
    contract_ids = {
        contract.contract_id
        for disaster in {case.scenario.disaster_type for case in cases.values()}
        for contract in repository.get_product_contracts(disaster)
    }
    kg_source_ids = {source.source_id for source in repository.list_data_sources()}
    rows = []
    for run in llm["runs"]:
        if run["case_id"] in P4_CASES:
            rows.append(
                _audit_run(
                    case=cases[run["case_id"]],
                    condition=run["knowledge_condition"],
                    plan=run.get("plan") or {},
                    source="llm",
                    contract_ids=contract_ids,
                    kg_source_ids=kg_source_ids,
                    tool_registry=tool_registry,
                    source_service=source_service,
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
                    contract_ids=contract_ids,
                    kg_source_ids=kg_source_ids,
                    tool_registry=tool_registry,
                    source_service=source_service,
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
    contract_ids: set[str],
    kg_source_ids: set[str],
    tool_registry: Any,
    source_service: SourceAssetService,
) -> dict[str, Any]:
    blockers = []
    missing_contracts = sorted(set(case.request_scope.contract_ids) - contract_ids)
    if missing_contracts:
        blockers.append("contract_not_resolved_in_kg")
    task_checks = []
    for task in plan.get("tasks", []):
        state = task.get("delivery_state")
        algorithm_id = task.get("algorithm_id")
        source_ids = [str(item) for item in task.get("source_ids", [])]
        executable_state = state in {"planned", "provisional", "degraded"}
        algorithm_registered = bool(algorithm_id and tool_registry.get(str(algorithm_id)))
        sources_grounded = all(source_id in kg_source_ids for source_id in source_ids)
        raw_sources_materializable = all(
            source_id.startswith("catalog.") or source_service.can_materialize(source_id)
            for source_id in source_ids
        )
        if executable_state and not algorithm_registered:
            blockers.append("executable_task_missing_registered_algorithm")
        if executable_state and not source_ids:
            blockers.append("executable_task_missing_source")
        if not sources_grounded:
            blockers.append("source_not_resolved_in_kg")
        if not raw_sources_materializable:
            blockers.append("raw_source_not_materializable")
        if executable_state and len(source_ids) != 1:
            blockers.append("workflow_task_requires_unambiguous_effective_source")
        task_checks.append(
            {
                "task_kind": task.get("task_kind"),
                "delivery_state": state,
                "algorithm_id": algorithm_id,
                "source_ids": source_ids,
                "algorithm_registered": algorithm_registered,
                "sources_grounded_in_kg": sources_grounded,
                "raw_sources_materializable_or_catalog": raw_sources_materializable,
            }
        )
    blockers.extend(
        [
            "research_plan_to_workflow_plan_adapter_missing",
            "selected_resolved_executed_evaluated_trace_missing",
        ]
    )
    unique_blockers = sorted(set(blockers))
    return {
        "case_id": case.case_id,
        "condition": condition,
        "source": source,
        "decision": plan.get("decision"),
        "contract_ids": list(case.request_scope.contract_ids),
        "task_checks": task_checks,
        "blockers": unique_blockers,
        "ready": not unique_blockers,
    }


def _blocker_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    blockers = sorted({blocker for row in rows for blocker in row["blockers"]})
    return {blocker: sum(blocker in row["blockers"] for row in rows) for blocker in blockers}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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
