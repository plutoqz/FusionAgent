from __future__ import annotations

import json
from pathlib import Path

from scripts.windows_runtime_doctor import build_doctor_report


def test_doctor_report_writes_runtime_evidence(tmp_path: Path) -> None:
    evidence_path = tmp_path / "doctor.json"
    report = build_doctor_report(
        repo_root=tmp_path,
        output_json=evidence_path,
        free_disk_gb=5.0,
    )

    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert payload["status"] in {"ready", "degraded"}
    assert payload["repo_root"] == str(tmp_path)
    assert report["known_limits"]["cross_platform"] == "out_of_scope"
