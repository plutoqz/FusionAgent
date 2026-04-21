from __future__ import annotations

from schemas.fusion import JobType
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
