import json
from pathlib import Path

from scripts.audit_p4_planning_e2e_readiness import audit_p4_readiness


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def test_p4_readiness_fails_closed_without_runtime_adapter(tmp_path):
    evaluation = {"automatic_checks": [], "automatic_score": 1.0}
    llm_runs = []
    deterministic_runs = []
    for case_id in ("C02", "C04", "C06"):
        for condition in ("llm_only", "llm_capability_kg", "llm_full_contract_kg"):
            llm_runs.append(
                {
                    "case_id": case_id,
                    "knowledge_condition": condition,
                    "plan": {"decision": "partial", "tasks": []},
                    "evaluation": evaluation,
                }
            )
        for group in ("fixed_workflow", "rules_only", "kg_only"):
            deterministic_runs.append(
                {
                    "case_id": case_id,
                    "group": group,
                    "plan": {"decision": "partial", "tasks": []},
                    "evaluation": evaluation,
                }
            )
    llm_path = tmp_path / "llm.json"
    deterministic_path = tmp_path / "det.json"
    llm_path.write_text(json.dumps({"runs": llm_runs}), encoding="utf-8")
    deterministic_path.write_text(json.dumps({"runs": deterministic_runs}), encoding="utf-8")

    report = audit_p4_readiness(
        llm_path=llm_path,
        deterministic_path=deterministic_path,
        manifest_path=MANIFEST,
        cache_dir=tmp_path / "cache",
    )

    assert report["audited_run_count"] == 18
    assert report["ready"] is False
    assert report["blocker_counts"]["research_plan_to_workflow_plan_adapter_missing"] == 18
