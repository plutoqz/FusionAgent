import json
from pathlib import Path

from scripts.audit_research_llm_preflight import audit_preflight


def test_preflight_audit_reports_hash_change_and_no_leak(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    current = tmp_path / "current.json"
    prior = tmp_path / "prior.json"
    manifest.write_text(
        json.dumps({"manifest_id": "case-set", "manifest_version": "1.1.0-draft"}),
        encoding="utf-8",
    )
    current.write_text(
        json.dumps([{"schedule": {"run_id": "r1"}, "input_hash": "sha256:new", "payload": {"request": {}}}]),
        encoding="utf-8",
    )
    prior.write_text(
        json.dumps([{"schedule": {"run_id": "r1"}, "input_hash": "sha256:old", "payload": {}}]),
        encoding="utf-8",
    )

    report = audit_preflight(
        manifest_path=manifest,
        prepared_path=current,
        prior_prepared_path=prior,
    )

    assert report["status"] == "passed"
    assert report["leak_count"] == 0
    assert report["prior_comparison"]["changed_input_hashes"] == 1


def test_preflight_audit_fails_on_gold_key(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    prepared = tmp_path / "prepared.json"
    manifest.write_text(
        json.dumps({"manifest_id": "case-set", "manifest_version": "1.1.0-draft"}),
        encoding="utf-8",
    )
    prepared.write_text(
        json.dumps(
            [
                {
                    "schedule": {"run_id": "r1"},
                    "input_hash": "sha256:bad",
                    "payload": {"observable_facts": {"expected_consequence": "answer"}},
                }
            ]
        ),
        encoding="utf-8",
    )

    report = audit_preflight(manifest_path=manifest, prepared_path=prepared)

    assert report["status"] == "failed"
    assert report["leak_count"] == 1
