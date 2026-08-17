from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


PACKET_VERSION = "fusionagent.research-manual-adjudication.v1"
ALLOWED_DECISIONS = ["fail", "not_assessable", "pass"]


def prepare_manual_adjudication(*, review_root: Path, output_root: Path) -> dict[str, Any]:
    if output_root.exists():
        raise RuntimeError(f"Refusing to overwrite adjudication packet root: {output_root}")

    agreement_path = review_root / "manual-review-agreement-audit.json"
    packet_manifest_path = review_root / "packet-manifest.json"
    reviewer_a_path = review_root / "reviewer-a.decisions.json"
    reviewer_b_path = review_root / "reviewer-b.decisions.json"
    reviewer_context_path = review_root / "reviewer-a.packet.json"
    agreement = _read_json(agreement_path)
    packet_manifest = _read_json(packet_manifest_path)
    reviewer_context = _read_json(reviewer_context_path)

    if agreement.get("disagreement_count", 0) <= 0:
        raise RuntimeError("Adjudication requires at least one frozen reviewer disagreement.")
    required_checks = {
        key: value
        for key, value in agreement.get("checks", {}).items()
        if key != "no_unresolved_disagreements"
    }
    if not required_checks or not all(required_checks.values()):
        raise RuntimeError("Source agreement audit failed integrity or completeness checks.")
    if agreement["source_packet_manifest"]["sha256"] != _file_hash(packet_manifest_path):
        raise RuntimeError("Packet manifest changed after the source agreement audit.")
    source_reviewer_paths = [reviewer_a_path, reviewer_b_path]
    for recorded, current in zip(agreement["reviewer_files"], source_reviewer_paths):
        if recorded["sha256"] != _file_hash(current):
            raise RuntimeError(f"Frozen reviewer decisions changed after agreement audit: {current}")
    expected_context_hash = packet_manifest["reviewers"]["reviewer-a"]["context_packet"]["sha256"]
    if expected_context_hash != _file_hash(reviewer_context_path):
        raise RuntimeError("Reviewer context changed before adjudication preparation.")

    context_by_id = {
        item["packet_item_id"]: item for item in reviewer_context.get("records", [])
    }
    disagreement_ids = {
        item["packet_item_id"] for item in agreement.get("disagreements", [])
    }
    if not disagreement_ids.issubset(context_by_id):
        raise RuntimeError("Reviewer context is missing one or more disagreement records.")
    records = [
        {
            "packet_item_id": item_id,
            "case_id": context_by_id[item_id]["case_id"],
            "visible_input": context_by_id[item_id]["visible_input"],
            "planner_output": context_by_id[item_id]["planner_output"],
            "rubric_item_id": context_by_id[item_id]["rubric_item_id"],
            "allowed_decisions": ALLOWED_DECISIONS,
        }
        for item_id in sorted(disagreement_ids)
    ]
    source_agreement_hash = _file_hash(agreement_path)
    packet_id = "adjudication-" + hashlib.sha256(
        f"{PACKET_VERSION}|{source_agreement_hash}".encode("utf-8")
    ).hexdigest()[:20]
    packet = {
        "packet_version": PACKET_VERSION,
        "packet_id": packet_id,
        "source_review_packet_id": packet_manifest["packet_id"],
        "source_agreement_audit_sha256": source_agreement_hash,
        "adjudicator_id": "adjudicator-c",
        "review_type": "independent human adjudication of frozen disagreements",
        "blinding_scope": [
            "knowledge condition, run id, replicate, and automatic scores omitted",
            "reviewer A and reviewer B decisions and notes omitted",
            "blind key remains excluded",
        ],
        "item_count": len(records),
        "records": records,
        "status": "immutable_adjudicator_context",
    }
    output_root.mkdir(parents=True)
    packet_path = output_root / "adjudicator-c.packet.json"
    decisions_path = output_root / "adjudicator-c.decisions.json"
    manifest_path = output_root / "adjudication-manifest.json"
    _write_json(packet_path, packet)
    _write_json(
        decisions_path,
        {
            "packet_version": PACKET_VERSION,
            "packet_id": packet_id,
            "source_agreement_audit_sha256": source_agreement_hash,
            "adjudicator_id": "adjudicator-c",
            "context_packet_sha256": _file_hash(packet_path),
            "records": [
                {
                    "packet_item_id": item["packet_item_id"],
                    "rubric_item_id": item["rubric_item_id"],
                    "decision": None,
                    "notes": "",
                }
                for item in records
            ],
            "status": "awaiting_human_adjudication",
        },
    )
    manifest = {
        "packet_version": PACKET_VERSION,
        "packet_id": packet_id,
        "source_review_packet_id": packet_manifest["packet_id"],
        "source_agreement_audit": _profile(agreement_path),
        "source_packet_manifest": _profile(packet_manifest_path),
        "source_reviewer_files": [_profile(path) for path in source_reviewer_paths],
        "item_count": len(records),
        "record_index_sha256": _record_index(records),
        "adjudicator_context": _profile(packet_path),
        "adjudicator_decisions": _profile(decisions_path),
        "status": "awaiting_independent_human_adjudication",
        "blind_key_used": False,
    }
    _write_json(manifest_path, manifest)
    return manifest


def _record_index(records: list[dict[str, Any]]) -> str:
    value = sorted(
        [
            {
                "packet_item_id": item["packet_item_id"],
                "rubric_item_id": item["rubric_item_id"],
            }
            for item in records
        ],
        key=lambda item: item["packet_item_id"],
    )
    return _semantic_hash(value)


def _profile(path: Path) -> dict[str, Any]:
    return {
        "path": str(path.resolve()),
        "size_bytes": path.stat().st_size,
        "sha256": _file_hash(path),
    }


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _semantic_hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare an independent blinded adjudication packet for frozen reviewer disagreements."
    )
    parser.add_argument("--review-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    prepare_manual_adjudication(review_root=args.review_root, output_root=args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
