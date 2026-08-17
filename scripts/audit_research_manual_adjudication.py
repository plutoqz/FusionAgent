from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ALLOWED_DECISIONS = {"pass", "fail", "not_assessable"}


def audit_manual_adjudication(
    *,
    adjudication_manifest: Path,
    adjudicator_decisions: Path,
    output: Path,
) -> dict[str, Any]:
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite adjudication audit: {output}")
    manifest = _read_json(adjudication_manifest)
    decisions = _read_json(adjudicator_decisions)
    agreement_path = Path(manifest["source_agreement_audit"]["path"])
    agreement = _read_json(agreement_path)
    source_reviewer_paths = [Path(item["path"]) for item in manifest["source_reviewer_files"]]
    reviewers = [_read_json(path) for path in source_reviewer_paths]
    context_path = Path(manifest["adjudicator_context"]["path"])
    context = _read_json(context_path)
    context_records = {
        item["packet_item_id"]: item for item in context.get("records", [])
    }
    decision_records = {
        item.get("packet_item_id"): item for item in decisions.get("records", [])
    }
    disagreement_ids = {
        item["packet_item_id"] for item in agreement.get("disagreements", [])
    }
    allowed_record_keys = {"packet_item_id", "rubric_item_id", "decision", "notes"}
    checks = {
        "manifest_packet_id": decisions.get("packet_id") == manifest.get("packet_id"),
        "source_agreement_unchanged": _file_hash(agreement_path)
        == manifest["source_agreement_audit"]["sha256"],
        "source_reviewer_files_unchanged": all(
            _file_hash(path) == recorded["sha256"]
            for path, recorded in zip(source_reviewer_paths, manifest["source_reviewer_files"])
        ),
        "context_unchanged": _file_hash(context_path) == manifest["adjudicator_context"]["sha256"],
        "context_hash_bound": decisions.get("context_packet_sha256")
        == manifest["adjudicator_context"]["sha256"],
        "source_agreement_bound": decisions.get("source_agreement_audit_sha256")
        == manifest["source_agreement_audit"]["sha256"],
        "adjudicator_identity": decisions.get("adjudicator_id") == "adjudicator-c",
        "context_item_count": len(context_records) == manifest.get("item_count"),
        "decision_item_count": len(decision_records) == manifest.get("item_count"),
        "exact_disagreement_set": set(context_records) == set(decision_records) == disagreement_ids,
        "record_index": _record_index(list(decision_records.values()))
        == manifest.get("record_index_sha256"),
        "decisions_complete": all(
            item.get("decision") in ALLOWED_DECISIONS for item in decision_records.values()
        ),
        "notes_complete": all(
            isinstance(item.get("notes"), str) and bool(item["notes"].strip())
            for item in decision_records.values()
        ),
        "records_remain_blinded": all(
            set(item).issubset(allowed_record_keys)
            and "knowledge_condition" not in item
            and "run_id" not in item
            and "replicate" not in item
            and "automatic_score" not in json.dumps(item, ensure_ascii=False)
            for item in decision_records.values()
        ),
    }
    source_by_id = [
        {item["packet_item_id"]: item for item in reviewer.get("records", [])}
        for reviewer in reviewers
    ]
    all_item_ids = set(source_by_id[0]) | set(source_by_id[1])
    final_records = []
    source_consensus_valid = True
    for item_id in sorted(all_item_ids):
        a = source_by_id[0].get(item_id)
        b = source_by_id[1].get(item_id)
        if a is None or b is None or a.get("rubric_item_id") != b.get("rubric_item_id"):
            source_consensus_valid = False
            continue
        if item_id in disagreement_ids:
            resolved = decision_records.get(item_id)
            if resolved is None:
                source_consensus_valid = False
                continue
            decision = resolved.get("decision")
            resolution_source = "independent_adjudicator_c"
        else:
            if a.get("decision") != b.get("decision"):
                source_consensus_valid = False
                continue
            decision = a.get("decision")
            resolution_source = "reviewer_a_b_agreement"
        final_records.append(
            {
                "packet_item_id": item_id,
                "rubric_item_id": a["rubric_item_id"],
                "decision": decision,
                "resolution_source": resolution_source,
            }
        )
    checks["source_consensus_complete"] = (
        source_consensus_valid and len(final_records) == len(all_item_ids)
    )
    passed = all(checks.values())
    counts = {
        decision: sum(item["decision"] == decision for item in final_records)
        for decision in sorted(ALLOWED_DECISIONS)
    }
    report = {
        "report_type": "research_manual_review_adjudication_audit",
        "packet_id": manifest.get("packet_id"),
        "source_review_packet_id": manifest.get("source_review_packet_id"),
        "source_adjudication_manifest": _profile(adjudication_manifest),
        "source_agreement_audit": _profile(agreement_path),
        "source_reviewer_files": [_profile(path) for path in source_reviewer_paths],
        "adjudicator_file": _profile(adjudicator_decisions),
        "checks": checks,
        "passed": passed,
        "adjudicated_item_count": len(decision_records),
        "final_item_count": len(final_records),
        "final_decision_counts": counts,
        "not_assessable_count": counts["not_assessable"],
        "manual_review_resolved": passed,
        "planning_claim_review_ready": passed and counts["not_assessable"] == 0,
        "final_blinded_decisions": final_records,
        "claim_boundary": (
            "This audit resolves only blinded planning rubric disagreements through an independent third "
            "human decision. It does not provide execution, product-quality, cross-AOI, or statistical evidence."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, report)
    return report


def _record_index(records: list[dict[str, Any]]) -> str:
    value = sorted(
        [
            {
                "packet_item_id": item.get("packet_item_id"),
                "rubric_item_id": item.get("rubric_item_id"),
            }
            for item in records
        ],
        key=lambda item: str(item["packet_item_id"]),
    )
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _profile(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "sha256": _file_hash(path),
    }


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit independent human adjudication of reviewer disagreements.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_manual_adjudication(
        adjudication_manifest=args.manifest,
        adjudicator_decisions=args.decisions,
        output=args.output,
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
