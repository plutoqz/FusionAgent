from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from api.app import create_app
import api.routers.settings as settings_router
from schemas.settings import EffectiveLLMSettings
from schemas.settings import PersistedLLMSettings
from services.runtime_settings_service import RuntimeSettingsService


@pytest.fixture(autouse=True)
def clear_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "GEOFUSION_LLM_PROVIDER",
        "GEOFUSION_LLM_BASE_URL",
        "GEOFUSION_LLM_API_KEY",
        "GEOFUSION_LLM_MODEL",
        "GEOFUSION_LLM_TIMEOUT_SEC",
        "OPENAI_API_KEY",
    ]:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def settings_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[TestClient, RuntimeSettingsService, list[EffectiveLLMSettings]]:
    monkeypatch.chdir(tmp_path)
    runtime_service = RuntimeSettingsService()
    refresh_calls: list[EffectiveLLMSettings] = []

    class FakeAgentRunService:
        def refresh_runtime_dependencies(self, llm_settings: EffectiveLLMSettings) -> None:
            refresh_calls.append(llm_settings)

    monkeypatch.setattr(settings_router, "runtime_settings_service", runtime_service)
    monkeypatch.setattr(settings_router, "agent_run_service", FakeAgentRunService())

    return TestClient(create_app()), runtime_service, refresh_calls


def test_get_llm_settings_returns_masked_persisted_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    RuntimeSettingsService().save_llm_settings(
        PersistedLLMSettings(
            provider="openai",
            base_url="https://persisted.example/v1",
            api_key="sk-persisted-secret-1234",
            model="gpt-persisted",
            timeout_sec=45,
        )
    )

    response = TestClient(create_app()).get("/api/v2/settings/llm")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "provider": "openai",
        "base_url": "https://persisted.example/v1",
        "model": "gpt-persisted",
        "timeout_sec": 45,
        "has_api_key": True,
        "api_key_masked": "sk-p...1234",
    }


def test_put_llm_settings_persists_patch_and_refreshes_runtime(
    settings_client: tuple[TestClient, RuntimeSettingsService, list[EffectiveLLMSettings]]
) -> None:
    client, runtime_service, refresh_calls = settings_client
    runtime_service.save_llm_settings(
        PersistedLLMSettings(
            provider="openai",
            base_url="https://persisted.example/v1",
            api_key="sk-persisted-secret-1234",
            model="gpt-persisted",
            timeout_sec=45,
        )
    )

    response = client.put(
        "/api/v2/settings/llm",
        json={
            "base_url": "https://updated.example/v1",
            "model": "gpt-updated",
            "timeout_sec": 90,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "provider": "openai",
        "base_url": "https://updated.example/v1",
        "model": "gpt-updated",
        "timeout_sec": 90,
        "has_api_key": True,
        "api_key_masked": "sk-p...1234",
    }
    assert runtime_service.get_effective_llm_settings() == EffectiveLLMSettings(
        provider="openai",
        base_url="https://updated.example/v1",
        api_key="sk-persisted-secret-1234",
        model="gpt-updated",
        timeout_sec=90,
    )
    assert refresh_calls == [
        EffectiveLLMSettings(
            provider="openai",
            base_url="https://updated.example/v1",
            api_key="sk-persisted-secret-1234",
            model="gpt-updated",
            timeout_sec=90,
        )
    ]


def test_put_llm_settings_rejects_openai_without_api_key(
    settings_client: tuple[TestClient, RuntimeSettingsService, list[EffectiveLLMSettings]]
) -> None:
    client, runtime_service, refresh_calls = settings_client

    response = client.put(
        "/api/v2/settings/llm",
        json={
            "provider": "openai",
            "base_url": "https://updated.example/v1",
            "model": "gpt-updated",
            "timeout_sec": 90,
        },
    )

    assert response.status_code == 422, response.text
    assert "api_key is required" in response.text
    assert runtime_service.get_llm_settings().has_api_key is False
    assert refresh_calls == []


def test_put_llm_settings_does_not_use_environment_api_key_for_validation(
    settings_client: tuple[TestClient, RuntimeSettingsService, list[EffectiveLLMSettings]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, runtime_service, refresh_calls = settings_client
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-secret-9999")

    response = client.put(
        "/api/v2/settings/llm",
        json={
            "provider": "openai",
            "model": "gpt-updated",
        },
    )

    assert response.status_code == 422, response.text
    assert "api_key is required" in response.text
    assert runtime_service.get_llm_settings().has_api_key is False
    assert refresh_calls == []


def test_validate_llm_settings_returns_masked_preview_without_persisting(
    settings_client: tuple[TestClient, RuntimeSettingsService, list[EffectiveLLMSettings]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, runtime_service, refresh_calls = settings_client
    runtime_service.save_llm_settings(
        PersistedLLMSettings(
            provider="openai",
            base_url="https://persisted.example/v1",
            api_key="sk-persisted-secret-1234",
            model="gpt-persisted",
            timeout_sec=45,
        )
    )
    probed: list[EffectiveLLMSettings] = []

    monkeypatch.setattr(settings_router, "probe_llm_settings", lambda llm_settings: probed.append(llm_settings))

    response = client.post(
        "/api/v2/settings/llm/validate",
        json={
            "model": "gpt-validated",
            "timeout_sec": 75,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "valid": True,
        "settings": {
            "provider": "openai",
            "base_url": "https://persisted.example/v1",
            "model": "gpt-validated",
            "timeout_sec": 75,
            "has_api_key": True,
            "api_key_masked": "sk-p...1234",
        },
    }
    assert runtime_service.get_effective_llm_settings() == EffectiveLLMSettings(
        provider="openai",
        base_url="https://persisted.example/v1",
        api_key="sk-persisted-secret-1234",
        model="gpt-persisted",
        timeout_sec=45,
    )
    assert probed == [
        EffectiveLLMSettings(
            provider="openai",
            base_url="https://persisted.example/v1",
            api_key="sk-persisted-secret-1234",
            model="gpt-validated",
            timeout_sec=75,
        )
    ]
    assert refresh_calls == []


def test_validate_llm_settings_rejects_openai_without_api_key(
    settings_client: tuple[TestClient, RuntimeSettingsService, list[EffectiveLLMSettings]]
) -> None:
    client, runtime_service, refresh_calls = settings_client

    response = client.post(
        "/api/v2/settings/llm/validate",
        json={
            "provider": "openai",
            "model": "gpt-validated",
        },
    )

    assert response.status_code == 422, response.text
    assert "api_key is required" in response.text
    assert runtime_service.get_llm_settings().has_api_key is False
    assert refresh_calls == []


def test_validate_llm_settings_does_not_use_environment_api_key_for_validation(
    settings_client: tuple[TestClient, RuntimeSettingsService, list[EffectiveLLMSettings]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, runtime_service, refresh_calls = settings_client
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-secret-9999")

    response = client.post(
        "/api/v2/settings/llm/validate",
        json={
            "provider": "openai",
            "model": "gpt-validated",
        },
    )

    assert response.status_code == 422, response.text
    assert "api_key is required" in response.text
    assert runtime_service.get_llm_settings().has_api_key is False
    assert refresh_calls == []


def test_put_llm_settings_explicit_empty_api_key_clears_persisted_secret(
    settings_client: tuple[TestClient, RuntimeSettingsService, list[EffectiveLLMSettings]]
) -> None:
    client, runtime_service, refresh_calls = settings_client
    runtime_service.save_llm_settings(
        PersistedLLMSettings(
            provider="mock",
            api_key="sk-persisted-secret-1234",
            model="persisted-model",
        )
    )

    response = client.put(
        "/api/v2/settings/llm",
        json={
            "api_key": "",
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "provider": "mock",
        "base_url": None,
        "model": "persisted-model",
        "timeout_sec": None,
        "has_api_key": False,
        "api_key_masked": None,
    }
    assert runtime_service.get_llm_settings() == PersistedLLMSettings(
        provider="mock",
        base_url=None,
        api_key=None,
        model="persisted-model",
        timeout_sec=None,
    ).masked_view()
    assert refresh_calls == [
        EffectiveLLMSettings(
            provider="mock",
            base_url=None,
            api_key=None,
            model="persisted-model",
            timeout_sec=None,
        )
    ]
