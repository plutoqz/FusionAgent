from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any


ALLOWED_DECISIONS = {"pass", "fail", "not_assessable"}
PACKET_VERSION = "fusionagent.research-manual-review.v1"


def prepare_manual_review(
    *,
    formal_root: Path,
    audit_path: Path,
    output_root: Path,
    packet_seed: int = 20260815,
) -> dict[str, Any]:
    if output_root.exists():
        raise RuntimeError(f"Refusing to overwrite review packet root: {output_root}")
    audit = _read_json(audit_path)
    if audit.get("evidence_integrity_valid") is not True:
        raise RuntimeError("Manual review requires evidence_integrity_valid=true")
    if audit.get("formal_execution_complete") is not True:
        raise RuntimeError("Manual review requires a complete 54-call formal batch")
    prepared = _read_json(formal_root / "prepared_inputs.json")
    prepared_by_id = {item["schedule"]["run_id"]: item for item in prepared}
    items = []
    blind_key = []
    for row in audit["runs"]:
        result = _read_json(formal_root / "runs" / row["run_id"] / "result.json")
        plan = result.get("plan")
        for manual_item in row["evaluation"]["manual_review_items"]:
            packet_item_id = _packet_item_id(
                packet_seed,
                row["run_id"],
                manual_item["item_id"],
            )
            items.append(
                {
                    "packet_item_id": packet_item_id,
                    "case_id": row["case_id"],
                    "visible_input": prepared_by_id[row["run_id"]]["payload"],
                    "planner_output": plan,
                    "rubric_item_id": manual_item["item_id"],
                    "allowed_decisions": sorted(ALLOWED_DECISIONS),
                }
            )
            blind_key.append(
                {
                    "packet_item_id": packet_item_id,
                    "run_id": row["run_id"],
                    "case_id": row["case_id"],
                    "knowledge_condition": row["knowledge_condition"],
                    "replicate": row["replicate"],
                    "rubric_item_id": manual_item["item_id"],
                }
            )
    if not items:
        raise RuntimeError("Formal audit contains no manual review items")
    random.Random(packet_seed).shuffle(items)
    packet_id = _packet_id(packet_seed, audit_path)
    packet = {
        "packet_version": PACKET_VERSION,
        "packet_id": packet_id,
        "source_audit_sha256": _file_hash(audit_path),
        "reviewer_scope": "two independent reviewers; no automatic decisions",
        "blinding_scope": [
            "knowledge_condition omitted from reviewer records",
            "run_id omitted from reviewer records",
            "replicate omitted from reviewer records",
            "automatic scores and automatic rubric results omitted",
            "gold rationale and prior machine-assisted decisions omitted",
            "knowledge condition may remain inferable from visible knowledge content; this is label and metadata blinding, not content masking",
        ],
        "item_count": len(items),
        "records": items,
        "status": "immutable_reviewer_context",
    }
    key = {
        "packet_version": PACKET_VERSION,
        "packet_id": packet_id,
        "source_audit_sha256": _file_hash(audit_path),
        "mapping": sorted(blind_key, key=lambda item: item["packet_item_id"]),
        "warning": "Keep this key separate from reviewer packets until both reviews are frozen.",
    }
    output_root.mkdir(parents=True)
    reviewer_a = output_root / "reviewer-a.packet.json"
    reviewer_b = output_root / "reviewer-b.packet.json"
    decisions_a = output_root / "reviewer-a.decisions.json"
    decisions_b = output_root / "reviewer-b.decisions.json"
    key_path = output_root / "blind-key.json"
    manifest_path = output_root / "packet-manifest.json"
    _write_json(reviewer_a, {**packet, "reviewer_id": "reviewer-a"})
    _write_json(reviewer_b, {**packet, "reviewer_id": "reviewer-b"})
    _write_json(decisions_a, _decision_template(packet, reviewer_a, "reviewer-a"))
    _write_json(decisions_b, _decision_template(packet, reviewer_b, "reviewer-b"))
    _write_json(key_path, key)
    manifest = {
        "packet_version": PACKET_VERSION,
        "packet_id": packet_id,
        "source_audit_sha256": _file_hash(audit_path),
        "packet_seed": packet_seed,
        "item_count": len(items),
        "review_record_index_sha256": _semantic_hash(
            sorted(
                [
                    {
                        "packet_item_id": item["packet_item_id"],
                        "rubric_item_id": item["rubric_item_id"],
                    }
                    for item in items
                ],
                key=lambda item: item["packet_item_id"],
            )
        ),
        "reviewers": {
            "reviewer-a": {
                "context_packet": _profile(reviewer_a),
                "decision_template": _profile(decisions_a),
            },
            "reviewer-b": {
                "context_packet": _profile(reviewer_b),
                "decision_template": _profile(decisions_b),
            },
        },
        "blind_key": _profile(key_path),
        "status": "awaiting_reviewer_decisions",
        "human_review_required": True,
    }
    _write_json(manifest_path, manifest)
    return manifest


def _decision_template(packet: dict[str, Any], packet_path: Path, reviewer_id: str) -> dict[str, Any]:
    return {
        "packet_version": PACKET_VERSION,
        "packet_id": packet["packet_id"],
        "source_audit_sha256": packet["source_audit_sha256"],
        "reviewer_id": reviewer_id,
        "context_packet_sha256": _file_hash(packet_path),
        "records": [
            {
                "packet_item_id": item["packet_item_id"],
                "rubric_item_id": item["rubric_item_id"],
                "decision": None,
                "notes": "",
            }
            for item in packet["records"]
        ],
        "status": "awaiting_human_review",
    }


def _packet_item_id(seed: int, run_id: str, item_id: str) -> str:
    value = f"{seed}|{run_id}|{item_id}".encode("utf-8")
    return "review-" + hashlib.sha256(value).hexdigest()[:20]


def _packet_id(seed: int, audit_path: Path) -> str:
    value = f"{PACKET_VERSION}|{seed}|{_file_hash(audit_path)}".encode("utf-8")
    return "packet-" + hashlib.sha256(value).hexdigest()[:20]


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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare blinded manual review packets for a complete formal batch.")
    parser.add_argument("--formal-root", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--packet-seed", type=int, default=20260815)
    args = parser.parse_args()
    prepare_manual_review(
        formal_root=args.formal_root,
        audit_path=args.audit,
        output_root=args.output,
        packet_seed=args.packet_seed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
