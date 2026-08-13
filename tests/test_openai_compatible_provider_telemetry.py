import json

import pytest

from llm.providers.openai_compatible import OpenAICompatibleProvider


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._body = json.dumps(payload).encode("utf-8")
        self.status = 200
        self.headers = {"x-request-id": "req-test-1"}

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def read(self) -> bytes:
        return self._body


def test_openai_provider_captures_usage_and_response_model(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="gpt-test-request",
        base_url="https://example.test/v1",
        max_output_tokens=8192,
    )
    response_payload = {
        "model": "gpt-test-response",
        "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "workflow_id": "wf_openai",
                            "tasks": [],
                        }
                    )
                }
            }
        ],
    }
    requests = []

    def fake_urlopen(request, timeout):
        requests.append(request)
        return _FakeResponse(response_payload)

    monkeypatch.setattr("llm.providers.openai_compatible.urllib.request.urlopen", fake_urlopen)

    plan = provider.generate_workflow_plan("system", {"intent": {"job_type": "building"}})
    sent_payload = json.loads(requests[0].data.decode("utf-8"))

    assert plan == {"workflow_id": "wf_openai", "tasks": []}
    assert provider.last_usage == {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}
    assert provider.last_model == "gpt-test-response"
    assert provider.last_attempt is not None
    assert provider.last_attempt["success"] is True
    assert provider.last_attempt["parse_mode"] == "strict_json"
    assert provider.last_attempt["request_id"] == "req-test-1"
    assert provider.last_attempt["finish_reason"] is None
    assert provider.last_attempt["raw_response"] == json.dumps(response_payload)
    assert sent_payload["max_tokens"] == 8192


def test_openai_provider_resets_usage_before_failed_request(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(api_key="test-key", model="gpt-test-request")
    provider.last_usage = {"prompt_tokens": 99, "completion_tokens": 1, "total_tokens": 100}
    provider.last_model = "stale-model"

    def fail_urlopen(request, timeout):
        raise OSError("network unavailable")

    monkeypatch.setattr("llm.providers.openai_compatible.urllib.request.urlopen", fail_urlopen)

    with pytest.raises(RuntimeError, match="LLM request failed"):
        provider.generate_workflow_plan("system", {"intent": {"job_type": "building"}})

    assert provider.last_usage is None
    assert provider.last_model == "gpt-test-request"
    assert provider.last_attempt is not None
    assert provider.last_attempt["success"] is False
    assert provider.last_attempt["failure_class"] == "transport_error"


def test_openai_provider_strict_mode_rejects_regex_salvage(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(
        api_key="test-key",
        model="gpt-test",
        allow_json_salvage=False,
    )
    response_payload = {
        "model": "gpt-test",
        "choices": [{"message": {"content": 'prefix {"workflow_id":"wf"} suffix'}}],
    }
    monkeypatch.setattr(
        "llm.providers.openai_compatible.urllib.request.urlopen",
        lambda request, timeout: _FakeResponse(response_payload),
    )

    with pytest.raises(ValueError, match="strict JSON"):
        provider.generate_workflow_plan("system", {"case_id": "C02"})

    assert provider.last_attempt is not None
    assert provider.last_attempt["success"] is False
    assert provider.last_attempt["parse_mode"] is None
    assert provider.last_attempt["failure_class"] == "semantic_parse_error"
    assert provider.last_attempt["raw_response"] == json.dumps(response_payload)


def test_openai_provider_marks_legacy_regex_salvage(monkeypatch) -> None:
    provider = OpenAICompatibleProvider(api_key="test-key", model="gpt-test")
    response_payload = {
        "model": "gpt-test",
        "choices": [{"message": {"content": 'prefix {"workflow_id":"wf","tasks":[]} suffix'}}],
    }
    monkeypatch.setattr(
        "llm.providers.openai_compatible.urllib.request.urlopen",
        lambda request, timeout: _FakeResponse(response_payload),
    )

    assert provider.generate_workflow_plan("system", {"case_id": "C02"})["workflow_id"] == "wf"
    assert provider.last_attempt is not None
    assert provider.last_attempt["parse_mode"] == "regex_salvage"
