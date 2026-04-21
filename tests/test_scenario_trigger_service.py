from __future__ import annotations

import json
from pathlib import Path

from schemas.fusion import JobType
from scripts import watch_scenario_inbox
from scripts.watch_scenario_inbox import process_inbox_once
from services.scenario_registry_service import ScenarioRegistryService
from services.scenario_trigger_service import normalize_trigger_event


def test_normalize_trigger_event_to_scenario_request():
    event = {
        "event_id": "usgs-2026-001",
        "event_type": "earthquake",
        "location": "Parakou, Benin",
        "requested_layers": ["building", "road"],
        "description": "M5 earthquake near Parakou",
    }

    request = normalize_trigger_event(event)

    assert request.disaster_type == "earthquake"
    assert request.job_types == [JobType.building, JobType.road]
    assert "Parakou, Benin" in request.trigger_content
    assert request.metadata["idempotency_key"] == "usgs-2026-001"
    assert request.metadata["event_id"] == "usgs-2026-001"
    assert request.metadata["trigger_event"] == event


def test_normalize_trigger_event_preserves_metadata_and_location_text():
    event = {
        "event_id": "gdacs-2026-017",
        "event_type": "flood",
        "location": "Nairobi, Kenya",
        "requested_layers": ["road"],
        "description": "River overflow near industrial area",
    }

    request = normalize_trigger_event(event)

    assert request.metadata["idempotency_key"] == "gdacs-2026-017"
    assert request.metadata["event_id"] == "gdacs-2026-017"
    assert request.metadata["trigger_event"] == event
    assert "Nairobi, Kenya" in request.trigger_content


def test_normalize_trigger_event_defaults_layers_and_hashes_missing_event_id():
    event = {
        "event_type": "flood",
        "location": "Nairobi, Kenya",
        "requested_layers": ["unknown"],
    }

    request_a = normalize_trigger_event(event)
    request_b = normalize_trigger_event(dict(reversed(list(event.items()))))

    assert request_a.job_types == [JobType.building, JobType.road]
    assert request_a.metadata["idempotency_key"] == request_b.metadata["idempotency_key"]


def test_process_inbox_once_moves_invalid_events_to_failed_dir(tmp_path, monkeypatch) -> None:
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    failed = tmp_path / "failed"
    inbox.mkdir()
    (inbox / "bad.json").write_text("{not json", encoding="utf-8")

    processed_ids = process_inbox_once(inbox, processed, output_root=str(tmp_path / "out"), failed_dir=failed)

    assert processed_ids == []
    assert not (inbox / "bad.json").exists()
    assert (failed / "bad.json").exists()


def test_process_inbox_once_returns_existing_scenario_for_duplicate_idempotency_key(tmp_path: Path, monkeypatch) -> None:
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    output_root = tmp_path / "out"
    inbox.mkdir()
    event = {
        "event_id": "usgs-2026-001",
        "event_type": "earthquake",
        "location": "Parakou, Benin",
        "requested_layers": ["building"],
    }
    (inbox / "event.json").write_text(json.dumps(event), encoding="utf-8")
    ScenarioRegistryService(output_root=output_root).record(
        {
            "scenario_id": "scenario-existing",
            "phase": "succeeded",
            "idempotency_key": "usgs-2026-001",
        }
    )

    def fail_create_scenario_run(request):
        raise AssertionError("duplicate idempotency key should not create a new scenario")

    monkeypatch.setattr(watch_scenario_inbox.scenario_run_service, "create_scenario_run", fail_create_scenario_run)

    processed_ids = process_inbox_once(inbox, processed, output_root=str(output_root))

    assert processed_ids == ["scenario-existing"]
    assert not (inbox / "event.json").exists()
    assert (processed / "event.json").exists()
