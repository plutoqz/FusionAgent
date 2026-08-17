from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def analyze_human_review(
    *,
    review_root: Path,
    adjudication_root: Path,
    output: Path,
) -> dict[str, Any]:
    if output.exists():
        raise RuntimeError(f"Refusing to overwrite unblinded human review analysis: {output}")
    packet_manifest_path = review_root / "packet-manifest.json"
    blind_key_path = review_root / "blind-key.json"
    agreement_path = review_root / "manual-review-agreement-audit.json"
    adjudication_manifest_path = adjudication_root / "adjudication-manifest.json"
    adjudication_audit_path = adjudication_root / "adjudication-audit.json"
    packet_manifest = _read_json(packet_manifest_path)
    blind_key = _read_json(blind_key_path)
    agreement = _read_json(agreement_path)
    adjudication_manifest = _read_json(adjudication_manifest_path)
    adjudication_audit = _read_json(adjudication_audit_path)

    checks = {
        "packet_manifest_hash": blind_key.get("source_audit_sha256")
        == packet_manifest.get("source_audit_sha256"),
        "adjudication_audit_passed": adjudication_audit.get("passed") is True,
        "adjudication_manifest_hash": adjudication_audit.get("source_adjudication_manifest", {}).get(
            "sha256"
        )
        == _file_hash(adjudication_manifest_path),
        "source_agreement_bound": adjudication_manifest.get("source_agreement_audit", {}).get(
            "sha256"
        )
        == _file_hash(agreement_path),
        "final_blinded_decisions_present": isinstance(
            adjudication_audit.get("final_blinded_decisions"), list
        ),
    }
    final_blinded = adjudication_audit.get("final_blinded_decisions", [])
    mapping = blind_key.get("mapping", [])
    mapping_by_id = {item.get("packet_item_id"): item for item in mapping}
    decisions_by_id = {item.get("packet_item_id"): item for item in final_blinded}
    checks.update(
        {
            "blind_key_unique_ids": len(mapping_by_id) == len(mapping) == 54,
            "final_decision_unique_ids": len(decisions_by_id) == len(final_blinded) == 54,
            "blind_key_final_id_set": set(mapping_by_id) == set(decisions_by_id),
            "final_decisions_complete": all(
                item.get("decision") in {"pass", "fail", "not_assessable"}
                for item in final_blinded
            ),
        }
    )
    if not all(checks.values()):
        raise RuntimeError(f"Unblinded human review gate failed: {checks}")

    rows = []
    for packet_item_id in sorted(mapping_by_id):
        key = mapping_by_id[packet_item_id]
        decision = decisions_by_id[packet_item_id]
        rows.append(
            {
                "packet_item_id": packet_item_id,
                "case_id": key["case_id"],
                "knowledge_condition": key["knowledge_condition"],
                "replicate": key["replicate"],
                "rubric_item_id": key["rubric_item_id"],
                "decision": decision["decision"],
                "resolution_source": decision["resolution_source"],
            }
        )
    by_condition = _summarize(rows, ["knowledge_condition"])
    by_case_condition = _summarize(rows, ["case_id", "knowledge_condition"])
    by_condition_rubric = _summarize(rows, ["knowledge_condition", "rubric_item_id"])
    adjudicated_count = sum(
        row["resolution_source"] == "independent_adjudicator_c" for row in rows
    )
    report = {
        "report_type": "method_b_unblinded_human_planning_review",
        "packet_id": packet_manifest["packet_id"],
        "source_files": {
            "packet_manifest": _profile(packet_manifest_path),
            "blind_key": _profile(blind_key_path),
            "agreement_audit": _profile(agreement_path),
            "adjudication_manifest": _profile(adjudication_manifest_path),
            "adjudication_audit": _profile(adjudication_audit_path),
        },
        "unblinding_gate": checks,
        "review_scope": {
            "item_count": len(rows),
            "adjudicated_item_count": adjudicated_count,
            "original_reviewer_agreement": agreement.get("agreement"),
            "adjudication_audit_passed": adjudication_audit["passed"],
        },
        "overall_decision_counts": dict(Counter(row["decision"] for row in rows)),
        "by_condition": by_condition,
        "by_case_condition": by_case_condition,
        "by_condition_rubric": by_condition_rubric,
        "rows": rows,
        "claim_eligible": False,
        "claim_boundary": (
            "Unblinded human planning review after independent adjudication. These counts describe the frozen "
            "planning packet only; they do not establish end-to-end product quality, cross-AOI validity, "
            "statistical significance, or superiority. The method B comparison remains post-held-out repair "
            "evidence and requires an independent confirmation set for a pristine formal claim."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, report)
    return report


def _summarize(rows: list[dict[str, Any]], group_fields: list[str]) -> list[dict[str, Any]]:
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[tuple(row[field] for field in group_fields)].append(row)
    result = []
    for key, items in sorted(groups.items(), key=lambda item: item[0]):
        counts = Counter(item["decision"] for item in items)
        result.append(
            {
                **dict(zip(group_fields, key)),
                "items": len(items),
                "pass": counts.get("pass", 0),
                "fail": counts.get("fail", 0),
                "not_assessable": counts.get("not_assessable", 0),
                "pass_rate": round(counts.get("pass", 0) / len(items), 6),
            }
        )
    return result


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
    parser = argparse.ArgumentParser(description="Summarize frozen human planning review after adjudication.")
    parser.add_argument("--review-root", type=Path, required=True)
    parser.add_argument("--adjudication-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = analyze_human_review(
        review_root=args.review_root,
        adjudication_root=args.adjudication_root,
        output=args.output,
    )
    return 0 if report["unblinding_gate"]["adjudication_audit_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
