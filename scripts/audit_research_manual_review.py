from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


ALLOWED_DECISIONS = {"pass", "fail", "not_assessable"}


def audit_manual_review(
    *,
    packet_manifest: Path,
    reviewer_a: Path,
    reviewer_b: Path,
    output: Path,
) -> dict[str, Any]:
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite manual review audit: {output}")
    manifest = _read_json(packet_manifest)
    packet_a = _read_json(reviewer_a)
    packet_b = _read_json(reviewer_b)
    expected_packet_id = manifest.get("packet_id")
    checks = {
        "packet_id_a": packet_a.get("packet_id") == expected_packet_id,
        "packet_id_b": packet_b.get("packet_id") == expected_packet_id,
        "source_audit_a": packet_a.get("source_audit_sha256") == manifest.get("source_audit_sha256"),
        "source_audit_b": packet_b.get("source_audit_sha256") == manifest.get("source_audit_sha256"),
        "item_count_a": len(packet_a.get("records", [])) == manifest.get("item_count"),
        "item_count_b": len(packet_b.get("records", [])) == manifest.get("item_count"),
        "reviewer_ids_distinct": packet_a.get("reviewer_id") == "reviewer-a"
        and packet_b.get("reviewer_id") == "reviewer-b",
        "context_packet_a": packet_a.get("context_packet_sha256")
        == manifest.get("reviewers", {}).get("reviewer-a", {}).get("context_packet", {}).get("sha256"),
        "context_packet_b": packet_b.get("context_packet_sha256")
        == manifest.get("reviewers", {}).get("reviewer-b", {}).get("context_packet", {}).get("sha256"),
    }
    records_a = {item.get("packet_item_id"): item for item in packet_a.get("records", [])}
    records_b = {item.get("packet_item_id"): item for item in packet_b.get("records", [])}
    checks["unique_item_ids_a"] = len(records_a) == len(packet_a.get("records", []))
    checks["unique_item_ids_b"] = len(records_b) == len(packet_b.get("records", []))
    checks["same_item_set"] = set(records_a) == set(records_b)
    checks["rubric_item_ids_match"] = all(
        records_a[item_id].get("rubric_item_id") == records_b[item_id].get("rubric_item_id")
        for item_id in set(records_a) & set(records_b)
    )
    checks["review_record_index_a"] = _review_record_index(records_a) == manifest.get(
        "review_record_index_sha256"
    )
    checks["review_record_index_b"] = _review_record_index(records_b) == manifest.get(
        "review_record_index_sha256"
    )
    invalid_a = [item.get("packet_item_id") for item in records_a.values() if item.get("decision") not in ALLOWED_DECISIONS]
    invalid_b = [item.get("packet_item_id") for item in records_b.values() if item.get("decision") not in ALLOWED_DECISIONS]
    checks["decisions_complete_a"] = not invalid_a
    checks["decisions_complete_b"] = not invalid_b
    comparisons = []
    for item_id in sorted(set(records_a) & set(records_b)):
        a = records_a[item_id].get("decision")
        b = records_b[item_id].get("decision")
        comparisons.append(
            {
                "packet_item_id": item_id,
                "decision_a": a,
                "decision_b": b,
                "agreement": a == b,
                "rubric_item_id": records_a[item_id].get("rubric_item_id"),
            }
        )
    agreement = _agreement(comparisons)
    per_item = {
        rubric_item: _agreement([item for item in comparisons if item["rubric_item_id"] == rubric_item])
        for rubric_item in sorted({item["rubric_item_id"] for item in comparisons})
    }
    disagreements = [item for item in comparisons if not item["agreement"]]
    checks["no_unresolved_disagreements"] = not disagreements
    allowed_record_keys = {"packet_item_id", "rubric_item_id", "decision", "notes"}
    checks["decision_records_remain_blinded"] = all(
        "knowledge_condition" not in item
        and "run_id" not in item
        and "replicate" not in item
        and "automatic_score" not in json.dumps(item, ensure_ascii=False)
        and set(item).issubset(allowed_record_keys)
        for item in records_a.values()
    ) and all(
        "knowledge_condition" not in item
        and "run_id" not in item
        and "replicate" not in item
        and "automatic_score" not in json.dumps(item, ensure_ascii=False)
        and set(item).issubset(allowed_record_keys)
        for item in records_b.values()
    )
    report = {
        "report_type": "research_manual_review_agreement_audit",
        "packet_id": expected_packet_id,
        "source_packet_manifest": _profile(packet_manifest),
        "reviewer_files": [_profile(reviewer_a), _profile(reviewer_b)],
        "checks": checks,
        "passed": all(checks.values()),
        "item_count": len(comparisons),
        "agreement": agreement,
        "per_rubric_item": per_item,
        "disagreement_count": len(disagreements),
        "disagreements": disagreements,
        "claim_boundary": (
            "Agreement statistics describe the frozen review packet only. They do not turn planning labels into "
            "execution evidence, and unresolved disagreements remain excluded from final claims."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, report)
    return report


def _agreement(comparisons: list[dict[str, Any]]) -> dict[str, Any]:
    if not comparisons:
        return {"items": 0, "exact_agreement": None, "cohen_kappa": None}
    pairs = [(item["decision_a"], item["decision_b"]) for item in comparisons]
    exact = sum(a == b for a, b in pairs) / len(pairs)
    categories = sorted({value for pair in pairs for value in pair})
    marginal_a = Counter(a for a, _ in pairs)
    marginal_b = Counter(b for _, b in pairs)
    expected = sum(
        (marginal_a[category] / len(pairs)) * (marginal_b[category] / len(pairs))
        for category in categories
    )
    if expected == 1.0:
        kappa = 1.0 if exact == 1.0 else 0.0
    else:
        kappa = (exact - expected) / (1.0 - expected)
    return {
        "items": len(pairs),
        "exact_agreement": round(exact, 6),
        "cohen_kappa": round(kappa, 6),
    }


def _profile(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "sha256": _file_hash(path),
    }


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _review_record_index(records: dict[str, dict[str, Any]]) -> str:
    value = sorted(
        [
            {
                "packet_item_id": item_id,
                "rubric_item_id": record.get("rubric_item_id"),
            }
            for item_id, record in records.items()
        ],
        key=lambda item: item["packet_item_id"],
    )
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit two blinded manual review files.")
    parser.add_argument("--packet-manifest", type=Path, required=True)
    parser.add_argument("--reviewer-a", type=Path, required=True)
    parser.add_argument("--reviewer-b", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = audit_manual_review(
        packet_manifest=args.packet_manifest,
        reviewer_a=args.reviewer_a,
        reviewer_b=args.reviewer_b,
        output=args.output,
    )
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
