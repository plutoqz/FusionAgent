from __future__ import annotations

import urllib.error
from io import BytesIO

import pytest

from api.routers.settings import probe_llm_settings
from llm.providers.openai_compatible import OpenAICompatibleProvider
from schemas.settings import EffectiveLLMSettings


class _Response:
    status = 200

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


def _openai_settings(**overrides: object) -> EffectiveLLMSettings:
    values: dict[str, object] = {
        "provider": "openai",
        "base_url": "https://llm.example/v1",
        "api_key": "sk-test-secret-1234",
        "model": "test-model",
        "timeout_sec": 7,
    }
    values.update(overrides)
    return EffectiveLLMSettings(**values)


def test_probe_mock_provider_does_not_make_network_request(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_urlopen(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("mock provider must not make a network request")

    monkeypatch.setattr("llm.providers.openai_compatible.urllib.request.urlopen", fail_urlopen)

    probe_llm_settings(EffectiveLLMSettings(provider="mock"))


def test_probe_openai_provider_uses_models_endpoint_and_configured_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, float, str]] = []

    def fake_urlopen(request: object, timeout: float) -> _Response:
        calls.append((request.full_url, timeout, request.get_header("Authorization")))
        return _Response()

    monkeypatch.setattr("llm.providers.openai_compatible.urllib.request.urlopen", fake_urlopen)

    probe_llm_settings(_openai_settings())

    assert calls == [("https://llm.example/v1/models", 7, "Bearer sk-test-secret-1234")]


def test_probe_openai_provider_reports_http_error_without_response_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(*_args: object, **_kwargs: object) -> None:
        raise urllib.error.HTTPError(
            "https://llm.example/v1/models",
            401,
            "Unauthorized",
            {},
            BytesIO(b"secret response body"),
        )

    monkeypatch.setattr("llm.providers.openai_compatible.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="HTTP 401") as exc_info:
        probe_llm_settings(_openai_settings())

    assert "secret response body" not in str(exc_info.value)
    assert "sk-test-secret-1234" not in str(exc_info.value)


def test_probe_openai_provider_reports_timeout_without_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(*_args: object, **_kwargs: object) -> None:
        raise TimeoutError("socket timeout")

    monkeypatch.setattr("llm.providers.openai_compatible.urllib.request.urlopen", fake_urlopen)

    with pytest.raises(RuntimeError, match="timed out after 7 seconds") as exc_info:
        probe_llm_settings(_openai_settings())

    assert "sk-test-secret-1234" not in str(exc_info.value)
