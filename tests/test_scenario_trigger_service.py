from __future__ import annotations

import json
from pathlib import Path

import pytest

from schemas.fusion import JobType
from schemas.scenario import ScenarioRunRequest
from schemas.task_kind import TaskKind
from scripts import watch_scenario_inbox
from scripts.watch_scenario_inbox import process_inbox_once
from services.mission_compiler_service import compile_scenario_mission
from services.scenario_registry_service import ScenarioRegistryService
from services.scenario_run_service import ScenarioRunService
from services.scenario_trigger_service import normalize_trigger_event
from tests.test_scenario_run_service import _FakeAgentRunService


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


def test_normalize_trigger_event_unsupported_layers_hashes_missing_event_id():
    event = {
        "event_type": "flood",
        "location": "Nairobi, Kenya",
        "requested_layers": ["unknown"],
    }

    request_a = normalize_trigger_event(event)
    request_b = normalize_trigger_event(dict(reversed(list(event.items()))))

    assert request_a.job_types == []
    assert request_a.metadata["requested_task_kinds"] == []
    assert request_a.metadata["requested_layers_present"] is True
    assert request_a.metadata["unsupported_requested_layers"] == ["unknown"]
    assert request_a.metadata["idempotency_key"] == request_b.metadata["idempotency_key"]


def test_normalize_trigger_event_without_requested_layers_leaves_scope_to_mission_compiler() -> None:
    event = {
        "event_id": "gdacs-2026-018",
        "event_type": "flood",
        "location": "Karachi, Pakistan",
        "description": "Urban flooding",
    }

    request = normalize_trigger_event(event)

    assert request.disaster_type == "flood"
    assert request.job_types == []
    assert request.metadata["requested_task_kinds"] == []
    assert request.metadata["requested_layers_present"] is False
    assert request.metadata["unsupported_requested_layers"] == []


def test_trigger_event_without_requested_layers_compiles_default_disaster_bundle() -> None:
    event = {
        "event_id": "gdacs-2026-022",
        "event_type": "flood",
        "location": "Karachi, Pakistan",
        "description": "Urban flooding",
    }

    request = normalize_trigger_event(event)
    mission = compile_scenario_mission(request)

    assert request.metadata["requested_layers_present"] is False
    assert mission.scope_source == "default_disaster_bundle"
    assert [task.task_kind for task in mission.child_tasks] == [
        TaskKind.building,
        TaskKind.road,
        TaskKind.water_polygon,
        TaskKind.waterways,
        TaskKind.poi,
    ]


def test_normalize_trigger_event_records_water_family_as_two_task_kinds() -> None:
    event = {
        "event_id": "gdacs-2026-019",
        "event_type": "flood",
        "location": "Nairobi, Kenya",
        "requested_layers": ["water"],
    }

    request = normalize_trigger_event(event)

    assert request.job_types == [JobType.water]
    assert request.metadata["requested_task_kinds"] == ["water_polygon", "waterways"]


def test_normalize_trigger_event_can_request_waterways_only() -> None:
    event = {
        "event_id": "gdacs-2026-020",
        "event_type": "flood",
        "location": "Sindh, Pakistan",
        "requested_layers": ["waterways"],
    }

    request = normalize_trigger_event(event)

    assert request.job_types == [JobType.water]
    assert request.metadata["requested_task_kinds"] == ["waterways"]


def test_normalize_trigger_event_records_unsupported_requested_layers() -> None:
    event = {
        "event_type": "flood",
        "location": "Nairobi, Kenya",
        "requested_layers": ["road", "traffic"],
    }

    request = normalize_trigger_event(event)

    assert request.job_types == [JobType.road]
    assert request.metadata["unsupported_requested_layers"] == ["traffic"]


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


def test_process_inbox_once_creates_exactly_one_scenario_run_for_single_event(
    tmp_path: Path,
    monkeypatch,
) -> None:
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    output_root = tmp_path / "out"
    inbox.mkdir()
    (inbox / "event.json").write_text(
        json.dumps(
            {
                "event_id": "usgs-2026-001",
                "event_type": "earthquake",
                "location": "Parakou, Benin",
                "requested_layers": ["building"],
            }
        ),
        encoding="utf-8",
    )
    calls: list[ScenarioRunRequest] = []

    def create_scenario_run(request: ScenarioRunRequest):
        calls.append(request)
        return type("ScenarioResponse", (), {"scenario_id": "scenario-created"})()

    monkeypatch.setattr(
        watch_scenario_inbox.scenario_run_service,
        "create_scenario_run",
        create_scenario_run,
    )

    processed_ids = process_inbox_once(inbox, processed, output_root=str(output_root))

    assert processed_ids == ["scenario-created"]
    assert len(calls) == 1
    assert calls[0].metadata["idempotency_key"] == "usgs-2026-001"
    assert calls[0].output_root == str(output_root)
    assert not (inbox / "event.json").exists()
    assert (processed / "event.json").exists()


def test_process_inbox_once_does_not_overwrite_existing_failed_event(tmp_path) -> None:
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    failed = tmp_path / "failed"
    inbox.mkdir()
    failed.mkdir()
    (inbox / "bad.json").write_text("{not json", encoding="utf-8")
    (failed / "bad.json").write_text("existing evidence", encoding="utf-8")

    processed_ids = process_inbox_once(inbox, processed, output_root=str(tmp_path / "out"), failed_dir=failed)

    assert processed_ids == []
    assert (failed / "bad.json").read_text(encoding="utf-8") == "existing evidence"
    assert (failed / "bad.1.json").read_text(encoding="utf-8") == "{not json"
    assert not (inbox / "bad.json").exists()


def test_process_inbox_once_does_not_overwrite_existing_processed_event(tmp_path: Path, monkeypatch) -> None:
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    output_root = tmp_path / "out"
    inbox.mkdir()
    processed.mkdir()
    event = {
        "event_id": "usgs-2026-001",
        "event_type": "earthquake",
        "location": "Parakou, Benin",
        "requested_layers": ["building"],
    }
    event_json = json.dumps(event)
    (inbox / "event.json").write_text(event_json, encoding="utf-8")
    (processed / "event.json").write_text("existing processed evidence", encoding="utf-8")
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
    assert (processed / "event.json").read_text(encoding="utf-8") == "existing processed evidence"
    assert (processed / "event.1.json").read_text(encoding="utf-8") == event_json
    assert not (inbox / "event.json").exists()


def test_process_inbox_once_without_failed_dir_keeps_fail_fast_and_leaves_invalid_event(tmp_path) -> None:
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    inbox.mkdir()
    (inbox / "bad.json").write_text("{not json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        process_inbox_once(inbox, processed, output_root=str(tmp_path / "out"), failed_dir=None)

    assert (inbox / "bad.json").read_text(encoding="utf-8") == "{not json"
    assert not processed.exists() or not any(processed.iterdir())


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


def test_scenario_run_service_registry_record_includes_trigger_metadata(tmp_path: Path) -> None:
    event = {
        "event_id": "usgs-2026-001",
        "event_type": "earthquake",
        "location": "Parakou, Benin",
    }
    service = ScenarioRunService(agent_run_service=_FakeAgentRunService(tmp_path))

    service.create_scenario_run(
        ScenarioRunRequest(
            scenario_name="Parakou earthquake",
            trigger_content="fuse building data for Parakou, Benin after an earthquake",
            disaster_type="earthquake",
            job_types=[JobType.building],
            output_root=str(tmp_path / "scenarios"),
            metadata={
                "idempotency_key": "usgs-2026-001",
                "trigger_event": event,
            },
        )
    )

    records = ScenarioRegistryService(output_root=tmp_path / "scenarios").list_records()

    assert records[0]["idempotency_key"] == "usgs-2026-001"
    assert records[0]["trigger_event"] == event
