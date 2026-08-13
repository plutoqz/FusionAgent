from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DECISIONS: dict[str, dict[str, dict[str, tuple[str, str]]]] = {
    "C01": {
        "llm_capability_kg": {
            "no_invalid_partial_building_claim": (
                "fail",
                "Building task is marked planned although building_partial_coverage_allowed=false and the gold requires pending or gap.",
            )
        },
        "llm_full_contract_kg": {
            "no_invalid_partial_building_claim": (
                "pass",
                "Building task is explicitly marked gap and no partial building delivery is claimed.",
            )
        },
        "llm_only": {
            "no_invalid_partial_building_claim": (
                "fail",
                "Building task is marked planned despite delayed Microsoft building data and the no-partial-coverage constraint.",
            )
        },
    },
    "C02": {
        condition: {
            "source_mismatch_gap": (
                "pass",
                "The plan declares building and POI gaps when those sources are absent and records source mapping uncertainty where present.",
            ),
            "no_silent_final_claim": (
                "pass",
                "The overall decision is partial and constrained layers are marked gap; no unrestricted final claim is made for missing layers.",
            ),
        }
        for condition in ("llm_only", "llm_capability_kg", "llm_full_contract_kg")
    },
    "C03": {},
    "C04": {
        "llm_capability_kg": {
            "background_pending": ("pass", "The plan identifies delayed raw.microsoft.road and the missing dual-source input."),
            "supersession": ("fail", "The plan does not express an initial provisional artifact being superseded by a later final artifact."),
            "coverage_gap": ("pass", "The plan explicitly marks the OSM-only result degraded and records the missing reference source as a quality uncertainty."),
        },
        "llm_full_contract_kg": {
            "background_pending": ("pass", "The plan identifies delayed raw.microsoft.road and the unavailable nominal dual-source bundle."),
            "supersession": ("fail", "The plan does not express an initial provisional artifact being superseded by a later final artifact."),
            "coverage_gap": ("pass", "The plan marks OSM-only delivery degraded and records the missing Microsoft reference source."),
        },
        "llm_only": {
            "background_pending": ("pass", "The plan acknowledges raw.microsoft.road is delayed."),
            "supersession": ("fail", "The plan claims planned delivery and does not express provisional-to-final supersession."),
            "coverage_gap": ("fail", "The plan does not mark the missing Microsoft reference as a coverage or delivery gap."),
        },
    },
    "C05": {
        condition: {
            "conflict_aware_fusion": (
                "pass",
                "The plan preserves OSM geometry versus Microsoft height tradeoff and states that a conflict report is required."),
            "provenance_complete": (
                "pending",
                "Source IDs and evidence are present, but completeness of lineage/provenance is an execution-time property not provable from planning output alone."),
            "quality_risk_or_unresolved_conflict": (
                "pass",
                "The plan records unresolved source conflict or quality uncertainty and, where applicable, uses provisional delivery."),
        }
        for condition in ("llm_only", "llm_capability_kg", "llm_full_contract_kg")
    },
    "C06": {
        condition: {
            "quality_failed_evidence": (
                "pass",
                "The plan cites the observed quality_gate_rejected_fusion_output and quality_gate_accepted=false."),
            "semantic_guard": (
                "pass",
                "The plan uses the observed quality failure and does not reclassify it as an external source failure or manual source removal."),
            "recovery_trace": (
                "pass",
                "The plan traces initial sources, recovery source raw.osm.road, recoverability, and degraded recovery posture."),
        }
        for condition in ("llm_only", "llm_capability_kg", "llm_full_contract_kg")
    },
}


def review_formal(root: Path) -> dict[str, Any]:
    audit = _read_json(root / "formal_automatic_audit.json")
    records = []
    for row in audit["runs"]:
        case_id = row["case_id"]
        condition = row["knowledge_condition"]
        for item in row["evaluation"]["manual_review_items"]:
            status, rationale = DECISIONS.get(case_id, {}).get(condition, {}).get(
                item["item_id"],
                ("pending", "No conservative manual ruling was encoded; execution evidence is required."),
            )
            records.append(
                {
                    "run_id": row["run_id"],
                    "case_id": case_id,
                    "knowledge_condition": condition,
                    "item_id": item["item_id"],
                    "status": status,
                    "rationale": rationale,
                }
            )
    counts = {status: sum(item["status"] == status for item in records) for status in ("pass", "fail", "pending")}
    return {
        "report_type": "planning_only_formal_manual_review",
        "protocol_id": audit["protocol_id"],
        "review_basis": "formal_automatic_audit.json plus frozen case gold rubric and visible planner observations",
        "records": records,
        "counts": counts,
        "claim_eligible": counts["fail"] == 0 and counts["pending"] == 0,
        "status": "complete" if counts["pending"] == 0 else "pending_execution_evidence",
        "boundary": "Manual review findings are diagnostic for this single repetition; they do not establish superiority or statistical significance.",
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Record conservative manual review for a formal planning run.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = review_formal(args.root)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
