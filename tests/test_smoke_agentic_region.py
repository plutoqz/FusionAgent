from __future__ import annotations

from scripts.smoke_agentic_region import build_create_run_form, parse_args


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
