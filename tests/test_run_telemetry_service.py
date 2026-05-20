import json

from schemas.agent import RunEvent, RunPhase, RunStatus, RunTrigger, RunTriggerType
from schemas.fusion import JobType
from services.run_telemetry_service import (
    build_run_telemetry_summary,
    estimate_json_size_bytes,
    normalize_llm_usage,
)


def test_estimate_json_size_bytes_matches_sorted_utf8_json_length() -> None:
    payload = {"z": "末尾", "a": [1, {"b": True}]}

    size = estimate_json_size_bytes(payload)

    expected = len(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"))
    assert size == expected


def test_normalize_llm_usage_accepts_openai_style_payload() -> None:
    normalized = normalize_llm_usage(
        {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}
    )

    assert normalized == {
        "prompt_tokens": 10,
        "completion_tokens": 4,
        "total_tokens": 14,
    }


def test_normalize_llm_usage_returns_none_for_missing_or_invalid_values() -> None:
    normalized = normalize_llm_usage(
        {"prompt_tokens": "10", "completion_tokens": "nope", "total_tokens": -1}
    )

    assert normalized == {
        "prompt_tokens": 10,
        "completion_tokens": None,
        "total_tokens": None,
    }


def test_normalize_llm_usage_handles_non_mapping_inputs_defensively() -> None:
    assert normalize_llm_usage("not-a-dict") == {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }


def test_build_run_telemetry_summary_uses_status_planning_telemetry() -> None:
    status = RunStatus(
        run_id="run-telemetry",
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        phase=RunPhase.succeeded,
        target_crs="EPSG:32643",
        planning_telemetry={"provider": "mock", "model": "mock-model", "elapsed_ms": 12},
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:01+00:00",
    )
    events = [
        RunEvent(
            timestamp="2026-05-20T00:00:00+00:00",
            kind="plan_created",
            phase=RunPhase.planning,
            message="plan",
            details={"grounding_score": 1.0},
        ),
        RunEvent(
            timestamp="2026-05-20T00:00:01+00:00",
            kind="run_succeeded",
            phase=RunPhase.succeeded,
            message="ok",
        ),
    ]

    summary = build_run_telemetry_summary(status=status, audit_events=events, plan=None)

    assert summary["planning"]["provider"] == "mock"
    assert summary["planning"]["elapsed_ms"] == 12
    assert summary["audit_event_count"] == 2
    assert summary["event_counts"] == {"plan_created": 1, "run_succeeded": 1}
    assert summary["last_event_kind"] == "run_succeeded"
