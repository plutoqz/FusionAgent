import json

from services.run_telemetry_service import estimate_json_size_bytes, normalize_llm_usage


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
