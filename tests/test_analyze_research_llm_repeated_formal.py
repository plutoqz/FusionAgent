import json
import shutil
from pathlib import Path

from scripts.analyze_research_llm_repeated_formal import analyze_repeated_formal
from scripts.freeze_research_repeated_protocol import build_repeated_freeze, write_repeated_freeze


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def _build_completed_root(tmp_path: Path) -> Path:
    evidence_path = tmp_path / "model-revision.json"
    evidence_path.write_text(
        json.dumps(
            {
                "provider": "deepseek_official",
                "model": "deepseek-v4-flash",
                "revision": "provider-revision-2026-08-13",
                "immutable": True,
                "production_release": True,
                "evidence_source": "provider-issued model release record",
                "issued_at": "2026-08-13T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    freeze = tmp_path / "freeze"
    write_repeated_freeze(
        freeze,
        build_repeated_freeze(
            manifest_path=MANIFEST,
            implementation_commit="a" * 40,
            model_revision_evidence_path=evidence_path,
        ),
    )
    root = tmp_path / "formal"
    root.mkdir()
    for source, target in (
        ("formal_protocol.json", "formal_protocol.json"),
        ("freeze_audit.json", "freeze_audit.json"),
        ("formal_schedule.json", "schedule.json"),
        ("formal_prepared_inputs.json", "prepared_inputs.json"),
        ("model_revision_evidence.json", "model_revision_evidence.json"),
    ):
        shutil.copy2(freeze / source, root / target)
    protocol = _read(root / "formal_protocol.json")
    schedule = _read(root / "schedule.json")
    prepared = _read(root / "prepared_inputs.json")
    prepared_by_id = {item["schedule"]["run_id"]: item for item in prepared}
    cases = {item["case_id"]: item for item in _read(MANIFEST)["cases"]}
    for item in schedule["items"]:
        run_id = item["run_id"]
        run_dir = root / "runs" / run_id
        run_dir.mkdir(parents=True)
        result = {
            "run_id": run_id,
            "input_hash": prepared_by_id[run_id]["input_hash"],
            "success": True,
            "plan": _plan(cases[item["case_id"]]),
            "attempt": {
                "response_model": "deepseek-v4-flash",
                "http_status": 200,
                "finish_reason": "stop",
                "parse_mode": "strict_json",
                "raw_response": "{}",
                "transport_retry_count": 0,
                "latency_ms": 100,
                "usage": {"total_tokens": 10},
            },
        }
        _write(run_dir / "result.json", result)
    _write(
        root / "execution_config.json",
        {
            "protocol_id": protocol["protocol_id"],
            "model_revision": protocol["provider"]["model_revision"],
            "requested_model": protocol["provider"]["requested_model"],
            "base_url_host": protocol["provider"]["base_url_host"],
            "temperature": protocol["generation"]["temperature"],
            "response_format": protocol["generation"]["response_format"],
            "max_output_tokens": protocol["generation"]["max_output_tokens"],
            "token_budget": protocol["budget"]["batch_token_budget"],
            "transport_retries": protocol["generation"]["transport_retries"],
            "semantic_repairs": protocol["generation"]["semantic_repairs"],
            "json_salvage": protocol["generation"]["json_salvage"],
            "fallback": protocol["generation"]["fallback"],
        },
    )
    _write(
        root / "execution_identity.json",
        {
            "protocol_id": protocol["protocol_id"],
            "frozen_implementation_commit": protocol["implementation_commit"],
            "execution_commit": "b" * 40,
            "execution_commit_descends_from_frozen_implementation": True,
            "worktree_clean_at_start": True,
            "execute_provider_calls": True,
        },
    )
    _write(
        root / "formal_summary.json",
        {
            "status": "completed",
            "scheduled_calls": 54,
            "executed_calls": 54,
            "successful_calls": 54,
            "failed_calls": 0,
            "consumed_tokens": 540,
            "failed_calls_replaced": False,
            "manual_review_status": "pending",
        },
    )
    return root


def _plan(case: dict) -> dict:
    rubric = case["gold_rubric"]
    tasks = []
    for order, task_kind in enumerate(rubric.get("expected_task_kinds", []), start=1):
        allowed = rubric.get("allowed_delivery_states", {}).get(task_kind, ["gap"])
        tasks.append(
            {
                "order": order,
                "task_kind": task_kind,
                "source_ids": [],
                "algorithm_id": None,
                "delivery_state": allowed[0],
                "rationale": "frozen synthetic analyzer fixture",
            }
        )
    return {
        "decision": rubric["allowed_decisions"][0],
        "tasks": tasks,
        "uncertainties": [],
        "evidence": [],
    }


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_repeated_analyzer_accepts_complete_stable_batch(tmp_path: Path) -> None:
    root = _build_completed_root(tmp_path)

    report = analyze_repeated_formal(root)

    assert report["evidence_integrity_valid"] is True
    assert report["formal_execution_complete"] is True
    assert report["attempted_call_count"] == 54
    assert len(report["cell_stability"]) == 18
    assert len(report["evidence_manifest"]["result_files"]) == 54
    assert report["extension_gate"]["extension_required"] is False
    assert report["manual_review_item_count"] == 108


def test_repeated_analyzer_triggers_full_extension_for_structure_drift(tmp_path: Path) -> None:
    root = _build_completed_root(tmp_path)
    path = root / "runs" / "formal-v2-c05-llm_only-r2" / "result.json"
    result = _read(path)
    result["plan"]["tasks"][0]["delivery_state"] = "provisional"
    _write(path, result)

    report = analyze_repeated_formal(root)

    assert report["formal_execution_complete"] is True
    assert report["extension_gate"]["extension_required"] is True
    assert report["extension_gate"]["scope"] == "all_cases_and_all_llm_conditions"
    assert any(
        reason["trigger"] == "multiple_plan_structure_signatures"
        and reason["case_id"] == "C05"
        and reason["knowledge_condition"] == "llm_only"
        for reason in report["extension_gate"]["reasons"]
    )


def test_repeated_analyzer_preserves_valid_but_incomplete_prefix(tmp_path: Path) -> None:
    root = _build_completed_root(tmp_path)
    schedule = _read(root / "schedule.json")
    last_run_id = schedule["items"][-1]["run_id"]
    shutil.rmtree(root / "runs" / last_run_id)
    summary = _read(root / "formal_summary.json")
    summary.update(
        status="completed_with_observed_failures",
        executed_calls=53,
        successful_calls=53,
        consumed_tokens=530,
    )
    _write(root / "formal_summary.json", summary)

    report = analyze_repeated_formal(root)

    assert report["evidence_integrity_valid"] is True
    assert report["formal_execution_complete"] is False
    assert report["extension_gate"]["status"] == "not_evaluable_batch_incomplete"
    assert report["extension_gate"]["extension_required"] is None
