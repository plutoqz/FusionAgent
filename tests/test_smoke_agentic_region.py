from __future__ import annotations

import pytest

from scripts.smoke_agentic_region import build_create_run_form, parse_args, run_smoke


def test_smoke_agentic_region_parses_nairobi_request() -> None:
    parsed = parse_args(
        [
            "--base-url",
            "http://127.0.0.1:8010",
            "--query",
            "fuse building and road data for Nairobi, Kenya",
            "--job-type",
            "building",
        ]
    )

    assert parsed.base_url == "http://127.0.0.1:8010"
    assert parsed.query == "fuse building and road data for Nairobi, Kenya"
    assert parsed.job_type == "building"


def test_smoke_agentic_region_builds_task_driven_form_payload() -> None:
    parsed = parse_args(
        [
            "--base-url",
            "http://127.0.0.1:8010",
            "--query",
            "fuse building and road data for Nairobi, Kenya",
            "--job-type",
            "road",
            "--target-crs",
            "EPSG:4326",
        ]
    )

    payload = build_create_run_form(parsed)

    assert payload["job_type"] == "road"
    assert payload["trigger_type"] == "user_query"
    assert payload["trigger_content"] == "fuse building and road data for Nairobi, Kenya"
    assert payload["input_strategy"] == "task_driven_auto"
    assert payload["target_crs"] == "EPSG:4326"


def test_smoke_agentic_region_omits_target_crs_when_not_provided() -> None:
    parsed = parse_args(
        [
            "--base-url",
            "http://127.0.0.1:8010",
            "--query",
            "fuse building and road data for Nairobi, Kenya",
            "--job-type",
            "building",
        ]
    )

    payload = build_create_run_form(parsed)

    assert payload["job_type"] == "building"
    assert payload["trigger_type"] == "user_query"
    assert payload["trigger_content"] == "fuse building and road data for Nairobi, Kenya"
    assert payload["input_strategy"] == "task_driven_auto"
    assert "target_crs" not in payload


def test_smoke_agentic_region_accepts_water_and_poi_job_types() -> None:
    water = parse_args(
        [
            "--base-url",
            "http://127.0.0.1:8010",
            "--query",
            "need water polygons for Nairobi, Kenya",
            "--job-type",
            "water",
        ]
    )
    poi = parse_args(
        [
            "--base-url",
            "http://127.0.0.1:8010",
            "--query",
            "show hospitals in Nairobi, Kenya",
            "--job-type",
            "poi",
        ]
    )

    assert build_create_run_form(water)["job_type"] == "water"
    assert build_create_run_form(poi)["job_type"] == "poi"


def test_smoke_agentic_region_includes_preferred_pattern_id_when_provided() -> None:
    parsed = parse_args(
        [
            "--base-url",
            "http://127.0.0.1:8010",
            "--query",
            "need road data for Gilgit city, Pakistan",
            "--job-type",
            "road",
            "--preferred-pattern-id",
            "wp.road.fusioncode.segment_topology.v1",
        ]
    )

    payload = build_create_run_form(parsed)

    assert payload["preferred_pattern_id"] == "wp.road.fusioncode.segment_topology.v1"


def test_smoke_agentic_region_requires_explicit_job_type() -> None:
    with pytest.raises(SystemExit):
        parse_args(
            [
                "--base-url",
                "http://127.0.0.1:8010",
                "--query",
                "need road data for Gilgit, Pakistan",
            ]
        )


def test_smoke_agentic_region_uses_total_timeout_for_create_request(monkeypatch: pytest.MonkeyPatch) -> None:
    timeouts: list[float] = []

    def fake_json_request(method: str, url: str, *, form_data=None, timeout_sec: float = 30.0):
        timeouts.append(timeout_sec)
        if method == "POST":
            return {"run_id": "run-1"}
        if url.endswith("/api/v2/runs/run-1"):
            return {"phase": "succeeded"}
        if url.endswith("/api/v2/runs/run-1/inspection"):
            return {"audit_events": [], "artifact": {}}
        raise AssertionError(url)

    monkeypatch.setattr("scripts.smoke_agentic_region._json_request", fake_json_request)

    result = run_smoke(
        base_url="http://127.0.0.1:8011",
        query="need road data for Gilgit city, Pakistan",
        job_type="road",
        target_crs="",
        preferred_pattern_id="",
        timeout_sec=1200.0,
        poll_interval_sec=0.2,
    )

    assert result["run_id"] == "run-1"
    assert timeouts[0] == 1200.0
