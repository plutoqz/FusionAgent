from __future__ import annotations

from services.architecture_mvp_evidence_service import build_architecture_mvp_evidence


def test_architecture_mvp_evidence_maps_objections_to_metrics() -> None:
    evidence = build_architecture_mvp_evidence(
        validation_events=[
            {"enforcement_mode": "enforce", "rejected": True, "reason_code": "DEPRECATED_ALGORITHM"}
        ],
        repair_records=[
            {
                "policy_source": "repair.alternative_algorithm.v1",
                "candidate_actions": [{"action": "alternative_algorithm"}],
                "selected_action": {"action": "alternative_algorithm"},
                "skipped_actions": [],
            }
        ],
        durable_learning_summaries=[
            {
                "condition_key": "task=road|entity=wp.road.v7|aoi=medium|source_coverage=partial|failure=none|quality=quality_gate_passed",
                "adjustment": 0.04,
            }
        ],
    )

    assert evidence["kg_hard_constraints"]["validator_rejection_count"] == 1
    assert evidence["repair_strategy_policy"]["policy_sourced_repair_count"] == 1
    assert evidence["conditional_learning"]["conditioned_summary_count"] == 1
    assert evidence["claim_boundary"]["learning"] == "condition-specific policy hints, not autonomous optimization"
