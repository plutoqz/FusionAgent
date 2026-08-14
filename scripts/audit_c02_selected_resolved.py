from __future__ import annotations

import argparse
import hashlib
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


PROTOCOL_ID = "fusionagent.p4.c02-selected-resolved.s1"
EXPECTED_EXECUTABLE_TASK_KINDS = {"water_polygon", "waterways", "road"}
EXPECTED_GAP_TASK_KINDS = {"building", "poi"}


def audit_c02_selected_resolved(
    *,
    result_path: Path,
    schedule_path: Path,
    manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise RuntimeError(f"Refusing to overwrite existing S1 evidence root: {output_dir}")

    result = _read_json(result_path)
    schedule = _read_json(schedule_path)
    schedule_items = {item["run_id"]: item for item in schedule["items"]}
    run_id = str(result.get("run_id") or "")
    scheduled = schedule_items.get(run_id)
    if scheduled is None:
        raise ValueError(f"Formal result run_id is not present in schedule: {run_id}")
    if scheduled["case_id"] != "C02" or scheduled["knowledge_condition"] != "llm_full_contract_kg":
        raise ValueError("S1 requires the C02 llm_full_contract_kg formal result")

    manifest = load_research_case_manifest(manifest_path)
    case = next(item for item in manifest.cases if item.case_id == "C02")
    decision = ResearchPlanningDecision.model_validate(result["plan"])
    adapter = ResearchPlanRuntimeAdapter(
        InMemoryKGRepository(experience_policy="pinned_snapshot"),
        tool_registry=build_default_tool_registry(),
    )
    resolution = adapter.resolve(
        case=case,
        condition=scheduled["knowledge_condition"],
        decision=decision,
        complete_from_kg=True,
    )

    original_by_order = {task.order: task for task in decision.tasks}
    task_resolutions = resolution.task_resolutions
    resolved_kinds = {
        item.task_kind for item in task_resolutions if item.resolution_status == "resolved"
    }
    gap_kinds = {
        item.task_kind for item in task_resolutions if item.resolution_status == "not_executable"
    }
    selected_preserved = all(
        item.selected.get("algorithm_id") == original_by_order[item.order].algorithm_id
        and item.selected.get("source_ids") == original_by_order[item.order].source_ids
        for item in task_resolutions
        if item.order in original_by_order
    )
    kg_completed = [
        item
        for item in task_resolutions
        if item.resolved.get("resolution_basis") == "kg_workflow_pattern"
    ]
    checks = {
        "formal_result_success": result.get("success") is True,
        "schedule_run_identity_exact": scheduled["run_id"] == run_id,
        "case_and_condition_exact": scheduled["case_id"] == "C02"
        and scheduled["knowledge_condition"] == "llm_full_contract_kg",
        "selected_fields_preserved": selected_preserved,
        "kg_completion_explicit": resolution.resolved.get("completion_policy") == "kg_workflow_pattern",
        "kg_completion_count_expected": len(kg_completed) == 3,
        "executable_task_kinds_exact": resolved_kinds == EXPECTED_EXECUTABLE_TASK_KINDS,
        "gap_task_kinds_exact": gap_kinds == EXPECTED_GAP_TASK_KINDS,
        "all_resolved_tasks_have_basis": all(
            item.resolution_status != "resolved"
            or item.resolved.get("resolution_basis") == "kg_workflow_pattern"
            for item in task_resolutions
        ),
        "gap_tasks_not_executable": all(
            item.task_kind in EXPECTED_GAP_TASK_KINDS
            and item.resolution_status == "not_executable"
            for item in task_resolutions
            if item.task_kind in EXPECTED_GAP_TASK_KINDS
        ),
        "workflow_task_kinds_match": {
            task.task_id for task in (resolution.workflow_plan.tasks if resolution.workflow_plan else [])
        }
        == {
            "task.water.fusion",
            "task.waterways.fusion",
            "task.road.fusion",
        },
        "kg_identity_frozen": resolution.resolved["knowledge_identity"]
        == adapter.kg_repo.get_knowledge_identity(),
    }
    payload = {
        "report_type": "p4_c02_selected_resolved_s1_audit",
        "protocol_id": PROTOCOL_ID,
        "claim_eligible": False,
        "claim_boundary": (
            "This is a planning-to-runtime resolution audit only. It does not execute fusion, "
            "materialize external data, or prove C02 end-to-end capability."
        ),
        "case_identity": {
            "case_id": case.case_id,
            "case_version": case.version,
            "formal_run_id": run_id,
            "knowledge_condition": scheduled["knowledge_condition"],
            "input_variant": scheduled.get("input_variant"),
        },
        "inputs": {
            "formal_result": _file_ref(result_path),
            "formal_schedule": _file_ref(schedule_path),
            "case_manifest": _file_ref(manifest_path),
        },
        "selected": decision.model_dump(mode="json"),
        "resolved": resolution.model_dump(mode="json"),
        "checks": checks,
        "passed": all(checks.values()),
        "runtime_calls": {
            "llm_calls": 0,
            "provider_calls": 0,
            "fusion_runs": 0,
        },
    }
    output_dir.mkdir(parents=True)
    _write_json(output_dir / "selected_resolved_audit.json", payload)
    _write_json(output_dir / "resolution.json", resolution.model_dump(mode="json"))
    return payload


def _file_ref(path: Path) -> dict[str, Any]:
    return {"path": str(path.resolve()), "sha256": _sha256(path)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit C02 selected/resolved KG completion without execution.")
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / "docs/current/research-case-manifest-v1.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_c02_selected_resolved(
        result_path=args.result,
        schedule_path=args.schedule,
        manifest_path=args.manifest,
        output_dir=args.output,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
