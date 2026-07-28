from __future__ import annotations

import copy
import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from llm.providers.base import LLMProvider
from schemas.product_contract_stability import RunOutcome, StabilityScope
from scripts import run_product_contract_stability as stability


def _c02_decision() -> dict:
    return {
        "strategy_id": "critical_first_degraded_delivery",
        "priority_tiers": [
            ["road", "water_type_1", "water_type_2"],
            ["building"],
        ],
        "initial_delivery_layers": [
            "water_type_1",
            "water_type_2",
            "road",
            "building",
        ],
        "background_completion_layers": ["water_type_1", "water_type_2"],
        "not_delivered_layers": [],
        "layer_decisions": [
            {
                "layer": "water_type_1",
                "selected_algorithm": "algo.fusion.water_type_1.v1",
                "selected_sources": ["raw.hydrolakes.water"],
                "delivery_mode": "degraded",
            },
            {
                "layer": "water_type_2",
                "selected_algorithm": "algo.fusion.water_type_2.v1",
                "selected_sources": ["raw.hydrorivers.water"],
                "delivery_mode": "degraded",
            },
            {
                "layer": "road",
                "selected_algorithm": "algo.fusion.road.v1",
                "selected_sources": ["raw.osm.road"],
                "delivery_mode": "provisional",
            },
            {
                "layer": "building",
                "selected_algorithm": "algo.fusion.building.v1",
                "selected_sources": ["raw.osm.building"],
                "delivery_mode": "provisional",
            },
        ],
        "planner_gap_proposal": [
            {
                "layer": "water_type_1",
                "gap_type": "source_mismatch",
                "source_id": "raw.hydrolakes.water",
                "reason": "The polygon source has a grounded semantic mismatch.",
            },
            {
                "layer": "water_type_2",
                "gap_type": "source_mismatch",
                "source_id": "raw.hydrorivers.water",
                "reason": "The waterway source is stale.",
            },
        ],
        "supersession_plan": [
            {
                "layer": "water_type_1",
                "target_delivery_mode": "final",
                "trigger_source_ids": ["raw.hydrolakes.water"],
                "condition": "A suitable current source passes quality gates.",
            },
            {
                "layer": "water_type_2",
                "target_delivery_mode": "final",
                "trigger_source_ids": ["raw.hydrorivers.water"],
                "condition": "A fresh source passes quality gates.",
            },
        ],
        "rationale": "Prioritize flood-critical water and road layers.",
    }


class _AuditProvider(LLMProvider):
    def __init__(self, contexts: list[dict], decision: dict | None = None) -> None:
        self.contexts = contexts
        self.decision = decision or _c02_decision()
        self.model = "gpt-5.4-mini"
        self.base_url = "https://example.test/v1"
        self.last_model = self.model
        self.last_usage = None
        self.last_latency_ms = None

    @property
    def provider_name(self) -> str:
        return "audit_test"

    def generate_workflow_plan(self, system_prompt, context):
        self.contexts.append(copy.deepcopy(context))
        self.last_usage = {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }
        self.last_latency_ms = 12.5
        return copy.deepcopy(self.decision)


def test_frozen_protocol_builds_balanced_deterministic_150_run_schedule() -> None:
    protocol = stability.load_stability_protocol()
    first = stability.build_schedule(
        protocol,
        case_ids=protocol.case_ids,
        planners=protocol.planners,
        repetitions=protocol.formal_repetitions_per_case_planner,
    )
    second = stability.build_schedule(
        protocol,
        case_ids=protocol.case_ids,
        planners=protocol.planners,
        repetitions=protocol.formal_repetitions_per_case_planner,
    )

    assert first == second
    assert len(first) == 150
    for case_id in protocol.case_ids:
        for planner in protocol.planners:
            variants = {
                item["input_variant"]
                for item in first
                if item["case_id"] == case_id and item["planner"] == planner
            }
            assert variants == {0, 1, 2, 3, 4}


def test_development_batch_writes_hash_chained_audit_and_resumes(monkeypatch) -> None:
    monkeypatch.setattr(stability, "_git_state", lambda: ("test-commit", False))
    contexts: list[dict] = []

    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        summary = stability.run_stability_batch(
            output_dir=output_dir,
            scope=StabilityScope.DEVELOPMENT,
            case_ids=["C02"],
            planners=[
                "fixed",
                "kg_only",
                "llm_only",
                "llm_capability_kg",
                "llm_full_contract_kg",
            ],
            repetitions=2,
            provider_factory=lambda _planner: _AuditProvider(contexts),
        )
        records = stability.verify_audit_ledger(output_dir / "audit_ledger.jsonl")

        assert summary["run_count"] == 10
        assert summary["success_count"] == 10
        assert summary["failure_count"] == 0
        assert summary["claim_eligible"] is False
        assert len(records) == 10
        assert records[0].previous_record_hash is None
        assert all(
            records[index].previous_record_hash == records[index - 1].record_hash
            for index in range(1, len(records))
        )
        assert len(contexts) == 6
        assert all("expected_" not in json.dumps(context) for context in contexts)

        for record in records:
            run_dir = output_dir / record.artifact_dir
            for artifact in record.artifacts:
                path = run_dir / artifact.relative_path
                assert hashlib.sha256(path.read_bytes()).hexdigest() == artifact.sha256

        fixed_stability = summary["planner_summaries"]["fixed"]["semantic_stability"]
        assert fixed_stability["exact_decision_signature_agreement"] == 1.0
        assert (
            summary["planner_summaries"]["llm_full_contract_kg"]
            ["metric_distributions"]["overall_score"]["sample_sd"]
            == 0.0
        )

        resumed = stability.run_stability_batch(
            output_dir=output_dir,
            scope=StabilityScope.DEVELOPMENT,
            case_ids=["C02"],
            planners=[
                "fixed",
                "kg_only",
                "llm_only",
                "llm_capability_kg",
                "llm_full_contract_kg",
            ],
            repetitions=2,
            provider_factory=lambda _planner: pytest.fail("resume reran a completed LLM run"),
            resume=True,
        )

        assert resumed["run_count"] == 10
        assert len(stability.verify_audit_ledger(output_dir / "audit_ledger.jsonl")) == 10


def test_failed_llm_run_is_audited_without_metric_imputation(monkeypatch) -> None:
    monkeypatch.setattr(stability, "_git_state", lambda: ("test-commit", False))
    invalid = _c02_decision()
    invalid["planner_gap_proposal"][0]["gap_type"] = "quality_failed"
    contexts: list[dict] = []

    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        summary = stability.run_stability_batch(
            output_dir=output_dir,
            scope=StabilityScope.DEVELOPMENT,
            case_ids=["C02"],
            planners=["llm_only"],
            repetitions=1,
            provider_factory=lambda _planner: _AuditProvider(contexts, invalid),
        )
        record = stability.verify_audit_ledger(output_dir / "audit_ledger.jsonl")[0]

    assert summary["run_count"] == 1
    assert summary["success_count"] == 0
    assert summary["failure_count"] == 1
    assert summary["planner_summaries"]["llm_only"]["metric_distributions"] == {}
    assert record.outcome == RunOutcome.FAILED
    assert record.metrics is None
    assert record.semantic_decision is None
    assert record.failure_type == "LLMPlanningFailure"
    assert any(item.relative_path == "planning_failure.json" for item in record.artifacts)


def test_audit_ledger_tampering_is_detected(monkeypatch) -> None:
    monkeypatch.setattr(stability, "_git_state", lambda: ("test-commit", False))

    with tempfile.TemporaryDirectory() as temp_dir:
        output_dir = Path(temp_dir)
        stability.run_stability_batch(
            output_dir=output_dir,
            scope=StabilityScope.DEVELOPMENT,
            case_ids=["C02"],
            planners=["fixed"],
            repetitions=1,
        )
        ledger = output_dir / "audit_ledger.jsonl"
        payload = json.loads(ledger.read_text("utf-8"))
        payload["duration_ms"] = payload["duration_ms"] + 1
        ledger.write_text(json.dumps(payload) + "\n", encoding="utf-8")

        with pytest.raises(ValueError, match="hash mismatch"):
            stability.verify_audit_ledger(ledger)


def test_formal_scope_rejects_partial_protocol_selection() -> None:
    with tempfile.TemporaryDirectory() as temp_dir, pytest.raises(
        ValueError, match="frozen case order"
    ):
        stability.run_stability_batch(
            output_dir=Path(temp_dir),
            scope=StabilityScope.FORMAL,
            case_ids=["C02"],
            planners=["fixed"],
            repetitions=5,
        )


def test_formal_scope_rejects_dirty_worktree(monkeypatch) -> None:
    protocol = stability.load_stability_protocol()
    monkeypatch.setattr(stability, "_git_state", lambda: ("test-commit", True))

    with tempfile.TemporaryDirectory() as temp_dir, pytest.raises(
        RuntimeError, match="clean Git worktree"
    ):
        stability.run_stability_batch(
            output_dir=Path(temp_dir),
            scope=StabilityScope.FORMAL,
            case_ids=protocol.case_ids,
            planners=protocol.planners,
            repetitions=protocol.formal_repetitions_per_case_planner,
        )
