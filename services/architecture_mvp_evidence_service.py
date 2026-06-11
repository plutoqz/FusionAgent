from __future__ import annotations

from typing import Any


def build_architecture_mvp_evidence(
    *,
    validation_events: list[dict[str, Any]],
    repair_records: list[dict[str, Any]],
    durable_learning_summaries: list[dict[str, Any]],
) -> dict[str, Any]:
    rejected = [event for event in validation_events if event.get("rejected") is True]
    policy_sourced_repairs = [record for record in repair_records if record.get("policy_source")]
    conditioned = [
        summary
        for summary in durable_learning_summaries
        if _condition_key_has_required_dimensions(str(summary.get("condition_key") or ""))
    ]
    return {
        "kg_hard_constraints": {
            "validator_rejection_count": len(rejected),
            "reason_codes": sorted({str(event.get("reason_code")) for event in rejected if event.get("reason_code")}),
        },
        "repair_strategy_policy": {
            "policy_sourced_repair_count": len(policy_sourced_repairs),
            "policy_sources": sorted({str(record.get("policy_source")) for record in policy_sourced_repairs}),
        },
        "conditional_learning": {
            "conditioned_summary_count": len(conditioned),
            "nonzero_adjustment_count": sum(
                1 for summary in conditioned if float(summary.get("adjustment") or 0.0) != 0.0
            ),
        },
        "claim_boundary": {
            "kg": "KG state acts as runtime constraint, not only prompt context",
            "repair": "existing healing capabilities ordered and explained by policy/KG evidence",
            "learning": "condition-specific policy hints, not autonomous optimization",
        },
    }


def _condition_key_has_required_dimensions(condition_key: str) -> bool:
    required = ("task=", "entity=", "aoi=", "source_coverage=", "failure=", "quality=")
    return all(item in condition_key for item in required)
