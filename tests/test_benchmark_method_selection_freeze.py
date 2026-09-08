from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.audit_method_selection_freeze import audit
from schemas.benchmark_method_selection_freeze import MethodSelectionFreezeCandidate


ROOT = Path(__file__).resolve().parents[1]


def _hash(path: str) -> str:
    return "sha256:" + hashlib.sha256((ROOT / path).read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def test_freeze_candidate_audit_binds_hashes_and_keeps_gate_closed(tmp_path: Path):
    files = (
        "benchmark_platform/context.py",
        "benchmark_platform/oracle.py",
        "benchmark_platform/preflight.py",
        "benchmark_platform/projections.py",
        "benchmark_platform/selection.py",
        "schemas/benchmark_method_selection.py",
    )
    payload = {
        "candidate_id": "fusionagent.method-selection-freeze-candidate.v1",
        "status": "awaiting_independent_review",
        "protocol_id": "method-selection-protocol.v1",
        "implementation_branch": "codex/benchmark-platform-dev-r1",
        "implementation_files": files,
        "implementation_hashes": {path: _hash(path) for path in files},
        "tests_passed": 82,
        "provider_calls": 0,
        "judge_calls": 0,
        "formal_result_roots_created": 0,
        "confirmation_unsealed": False,
        "e2e_selected": False,
        "unresolved_review_items": ["independent_review", "user_freeze_approval"],
    }
    path = tmp_path / "candidate.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = audit(ROOT, path)
    assert result["passed"] is True
    assert result["independent_review_required"] is True
