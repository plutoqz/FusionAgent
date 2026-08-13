import json
from pathlib import Path

from scripts.audit_p4_planning_e2e_readiness import _read_llm_runs, audit_p4_readiness


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def test_p4_readiness_fails_closed_when_plans_have_no_executable_tasks(tmp_path):
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
    assert report["blocker_counts"]["no_executable_workflow_plan"] == 18
    assert "research_plan_to_workflow_plan_adapter_missing" not in report["blocker_counts"]


def test_read_llm_runs_loads_immutable_formal_result_layout(tmp_path):
    result_dir = tmp_path / "runs" / "formal-c02-llm_only-r1"
    result_dir.mkdir(parents=True)
    payload = {
        "run_id": "formal-c02-llm_only-r1",
        "plan": {"decision": "gap", "tasks": [], "uncertainties": [], "evidence": []},
    }
    (result_dir / "result.json").write_text(json.dumps(payload), encoding="utf-8")
    (tmp_path / "schedule.json").write_text(
        json.dumps(
            {
                "items": [
                    {
                        "run_id": "formal-c02-llm_only-r1",
                        "case_id": "C02",
                        "knowledge_condition": "llm_only",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert _read_llm_runs(tmp_path) == {
        "runs": [{**payload, "case_id": "C02", "knowledge_condition": "llm_only"}]
    }
