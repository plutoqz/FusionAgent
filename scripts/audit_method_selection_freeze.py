from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from schemas.benchmark_method_selection_freeze import MethodSelectionFreezeCandidate


def sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def audit(root: Path, candidate_path: Path) -> dict:
    candidate = MethodSelectionFreezeCandidate.model_validate(json.loads(candidate_path.read_text(encoding="utf-8")))
    failures = []
    for relative, expected in candidate.implementation_hashes.items():
        path = root / relative
        if not path.exists():
            failures.append({"path": relative, "reason": "missing"})
        elif sha256(path) != expected:
            failures.append({"path": relative, "reason": "hash_mismatch", "actual": sha256(path), "expected": expected})
    expected_accounting = candidate.provider_calls == candidate.judge_calls == candidate.formal_result_roots_created == 0
    if not expected_accounting or candidate.confirmation_unsealed or candidate.e2e_selected:
        failures.append({"reason": "authorization_boundary_violation"})
    return {"audit_id": "fusionagent.method-selection-freeze-audit.v1", "candidate_id": candidate.candidate_id, "status": candidate.status, "passed": not failures, "failures": failures, "independent_review_required": True}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    result = audit(root, args.candidate if args.candidate.is_absolute() else root / args.candidate)
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "failure_count": len(result["failures"])}, ensure_ascii=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
