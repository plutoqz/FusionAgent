from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from api.app import create_app
from schemas.fusion import JobType
from services.unsupported_intent_guard import classify_unsupported_intent


def test_preflight_rejects_trajectory_to_road_execution() -> None:
    response = TestClient(create_app()).post(
        "/api/v2/runs/preflight",
        json={
            "job_type": "road",
            "trigger": {
                "type": "user_query",
                "content": "run trajectory to road fusion now",
                "spatial_extent": "bbox(0,0,1,1)",
            },
            "input_strategy": "task_driven_auto",
        },
    )

    payload = response.json()
    assert payload["allowed"] is False
    assert any(item["code"] == "trajectory_to_road_deferred" for item in payload["unsupported_intent"])


def test_preflight_allows_bounded_building_road_water_poi() -> None:
    client = TestClient(create_app())
    for job_type in ["building", "road", "water", "poi"]:
        response = client.post(
            "/api/v2/runs/preflight",
            json={
                "job_type": job_type,
                "trigger": {
                    "type": "user_query",
                    "content": f"run bounded {job_type} fusion",
                    "spatial_extent": "bbox(0,0,1,1)",
                },
                "input_strategy": "task_driven_auto",
            },
        )
        assert response.status_code == 200
        assert response.json()["allowed"] is True


def test_preflight_reports_aoi_source_components_and_degradation_for_partial_sources() -> None:
    response = TestClient(create_app()).post(
        "/api/v2/runs/preflight",
        json={
            "job_type": "road",
            "trigger": {
                "type": "user_query",
                "content": "Karachi flood road fusion",
                "disaster_type": "flood",
                "spatial_extent": "bbox(66.28,24.42,67.58,25.67)",
            },
            "input_strategy": "task_driven_auto",
        },
    )

    payload = response.json()
    assert payload["allowed"] is True
    assert payload["aoi"]["bbox"] == [66.28, 24.42, 67.58, 25.67]
    assert payload["source_selection"]["selected_source_id"] == "catalog.flood.road"
    assert payload["component_coverage"]["required_source_ids"] == [
        "raw.osm.road",
        "raw.microsoft.road",
    ]
    assert payload["component_coverage"]["partial_coverage_allowed"] is True
    assert payload["degradation"]["state"] == "preflight_partial_allowed"


def test_preflight_rejects_unbounded_poi_entity_alignment() -> None:
    issues = classify_unsupported_intent("match all global POI entities without bbox", job_type=JobType.poi)
    assert any(item["code"] == "unsupported_unbounded_poi_entity_alignment" for item in issues)
