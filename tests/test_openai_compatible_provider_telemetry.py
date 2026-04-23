import json

import pytest

from llm.providers.openai_compatible import OpenAICompatibleProvider


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._body = json.dumps(payload).encode("utf-8")

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

    monkeypatch.setattr(
        "llm.providers.openai_compatible.urllib.request.urlopen",
        lambda request, timeout: _FakeResponse(response_payload),
    )

    plan = provider.generate_workflow_plan("system", {"intent": {"job_type": "building"}})

    assert plan == {"workflow_id": "wf_openai", "tasks": []}
    assert provider.last_usage == {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}
    assert provider.last_model == "gpt-test-response"


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
