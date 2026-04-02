from __future__ import annotations

import json
from pathlib import Path


def test_golden_case_manifest_contains_four_cases() -> None:
    root = Path("tests/golden_cases")
    case_files = sorted(root.glob("*/case.json"))

    assert len(case_files) == 4

    for case_file in case_files:
        payload = json.loads(case_file.read_text(encoding="utf-8"))
        assert payload["job_type"] in {"building", "road"}
        assert payload["trigger"]["type"] in {"user_query", "disaster_event"}
        assert payload["expected_plan_checks"]
        assert payload["artifact_checks"]
        assert (case_file.parent / payload["osm_zip"]).exists()
        assert (case_file.parent / payload["ref_zip"]).exists()
