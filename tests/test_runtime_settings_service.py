from __future__ import annotations

import os
from pathlib import Path

import pytest

from llm.factory import create_llm_provider
from llm.providers.openai_compatible import OpenAICompatibleProvider
from schemas.settings import EffectiveLLMSettings, PersistedLLMSettings
from services.runtime_settings_service import RuntimeSettingsService


MANAGED_ENV_KEYS = [
    "GEOFUSION_LLM_PROVIDER",
    "GEOFUSION_LLM_BASE_URL",
    "GEOFUSION_LLM_API_KEY",
    "GEOFUSION_LLM_MODEL",
    "GEOFUSION_LLM_TIMEOUT_SEC",
    "OPENAI_API_KEY",
]


@pytest.fixture(autouse=True)
def restore_managed_env() -> None:
    snapshot = {key: os.environ.get(key) for key in MANAGED_ENV_KEYS}
    yield
    for key, value in snapshot.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_runtime_settings_service_masks_api_key_when_loading_persisted_settings(tmp_path: Path) -> None:
    service = RuntimeSettingsService(settings_path=tmp_path / "tmp" / "runtime-settings" / "llm-settings.json")

    service.save_llm_settings(
        PersistedLLMSettings(
            provider="openai",
            base_url="https://persisted.example/v1",
            api_key="sk-persisted-secret-1234",
            model="persisted-model",
            timeout_sec=45,
        )
    )

    stored = service.get_llm_settings()

    assert stored.provider == "openai"
    assert stored.base_url == "https://persisted.example/v1"
    assert stored.model == "persisted-model"
    assert stored.timeout_sec == 45
    assert stored.has_api_key is True
    assert stored.api_key_masked is not None
    assert stored.api_key_masked != "sk-persisted-secret-1234"
    assert stored.api_key_masked.startswith("sk-p")
    assert stored.api_key_masked.endswith("1234")


def test_runtime_settings_service_merges_environment_overrides_into_effective_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = RuntimeSettingsService(settings_path=tmp_path / "tmp" / "runtime-settings" / "llm-settings.json")
    service.save_llm_settings(
        PersistedLLMSettings(
            provider="openai",
            base_url="https://persisted.example/v1",
            api_key="sk-persisted-secret-1234",
            model="persisted-model",
            timeout_sec=45,
        )
    )
    monkeypatch.setenv("GEOFUSION_LLM_PROVIDER", "mock")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env-secret-9999")
    monkeypatch.setenv("GEOFUSION_LLM_BASE_URL", "https://env.example/v1")
    monkeypatch.setenv("GEOFUSION_LLM_TIMEOUT_SEC", "90")

    effective = service.get_effective_llm_settings()

    assert effective == EffectiveLLMSettings(
        provider="mock",
        base_url="https://env.example/v1",
        api_key="sk-env-secret-9999",
        model="persisted-model",
        timeout_sec=90,
    )


def test_create_llm_provider_prefers_explicit_settings_over_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEOFUSION_LLM_PROVIDER", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEOFUSION_LLM_API_KEY", raising=False)

    provider = create_llm_provider(
        EffectiveLLMSettings(
            provider="openai",
            base_url="https://explicit.example/v1",
            api_key="sk-explicit-secret",
            model="gpt-explicit",
            timeout_sec=12,
        )
    )

    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.base_url == "https://explicit.example/v1"
    assert provider.api_key == "sk-explicit-secret"
    assert provider.model == "gpt-explicit"
    assert provider.timeout_sec == 12
