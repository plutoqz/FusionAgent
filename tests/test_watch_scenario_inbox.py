from __future__ import annotations

import json
from pathlib import Path

from scripts.watch_scenario_inbox import process_inbox_once


def test_process_inbox_once_writes_evidence_json_for_processed_and_failed_events(
    tmp_path: Path, monkeypatch
) -> None:
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    failed = tmp_path / "failed"
    evidence = tmp_path / "inbox_evidence.json"
    inbox.mkdir()
    (inbox / "good.json").write_text(
        json.dumps(
            {
                "event_id": "evt-good",
                "scenario_name": "nightly scenario",
                "disaster_type": "flood",
                "job_types": ["building"],
                "spatial_extent": "bbox(0,0,1,1)",
            }
        ),
        encoding="utf-8",
    )
    (inbox / "bad.json").write_text("{bad json", encoding="utf-8")

    import scripts.watch_scenario_inbox as module

    monkeypatch.setattr(
        module.scenario_run_service,
        "create_scenario_run",
        lambda request: type("Response", (), {"scenario_id": "scenario-good"})(),
    )

    processed_ids = process_inbox_once(
        inbox,
        processed,
        failed_dir=failed,
        evidence_json=evidence,
    )

    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert processed_ids == ["scenario-good"]
    assert payload["processed"] == ["scenario-good"]
    assert payload["failed"] == [{"filename": "bad.json", "error_type": "JSONDecodeError"}]
    assert payload["counts"] == {"processed": 1, "failed": 1, "idempotent": 0}


def test_process_inbox_once_records_idempotent_events_separately_in_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    output_root = tmp_path / "out"
    evidence = tmp_path / "inbox_evidence.json"
    inbox.mkdir()
    (inbox / "duplicate.json").write_text(
        json.dumps(
            {
                "event_id": "evt-duplicate",
                "event_type": "flood",
                "location": "Nairobi, Kenya",
                "requested_layers": ["poi"],
            }
        ),
        encoding="utf-8",
    )

    from services.scenario_registry_service import ScenarioRegistryService

    ScenarioRegistryService(output_root=output_root).record(
        {
            "scenario_id": "scenario-existing",
            "phase": "succeeded",
            "idempotency_key": "evt-duplicate",
        }
    )

    import scripts.watch_scenario_inbox as module

    monkeypatch.setattr(
        module.scenario_run_service,
        "create_scenario_run",
        lambda request: (_ for _ in ()).throw(AssertionError("duplicate should not create a scenario")),
    )

    processed_ids = process_inbox_once(
        inbox,
        processed,
        output_root=str(output_root),
        evidence_json=evidence,
    )

    payload = json.loads(evidence.read_text(encoding="utf-8"))
    assert processed_ids == ["scenario-existing"]
    assert payload["processed"] == []
    assert payload["idempotent"] == ["scenario-existing"]
    assert payload["all_scenario_ids"] == ["scenario-existing"]
    assert payload["counts"] == {"processed": 0, "failed": 0, "idempotent": 1}
