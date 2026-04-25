from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from llm.factory import create_llm_provider
from llm.providers.openai_compatible import OpenAICompatibleProvider
from llm.providers.mock_provider import MockLLMProvider
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


def test_runtime_settings_service_partial_save_preserves_existing_api_key(tmp_path: Path) -> None:
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

    stored = service.save_llm_settings(
        PersistedLLMSettings(
            provider="mock",
            model="patched-model",
        )
    )
    effective = service.get_effective_llm_settings()

    assert stored.provider == "mock"
    assert stored.model == "patched-model"
    assert stored.has_api_key is True
    assert effective.api_key == "sk-persisted-secret-1234"
    assert effective.base_url == "https://persisted.example/v1"


def test_runtime_settings_service_explicit_empty_api_key_clears_existing_secret(tmp_path: Path) -> None:
    service = RuntimeSettingsService(settings_path=tmp_path / "tmp" / "runtime-settings" / "llm-settings.json")
    service.save_llm_settings(
        PersistedLLMSettings(
            provider="openai",
            api_key="sk-persisted-secret-1234",
            model="persisted-model",
        )
    )

    stored = service.save_llm_settings(PersistedLLMSettings(api_key=""))
    effective = service.get_effective_llm_settings()

    assert stored.has_api_key is False
    assert stored.api_key_masked is None
    assert effective.api_key is None


def test_runtime_settings_service_deduplicates_runtime_snapshots(tmp_path: Path) -> None:
    service = RuntimeSettingsService(
        settings_path=tmp_path / "tmp" / "runtime-settings" / "llm-settings.json",
        snapshots_dir=tmp_path / "tmp" / "runtime-settings" / "snapshots",
    )
    settings = EffectiveLLMSettings(
        provider="openai",
        base_url="https://snapshot.example/v1",
        api_key="sk-snapshot-secret-1234",
        model="gpt-snapshot",
        timeout_sec=20,
    )

    first_snapshot_id = service.store_runtime_snapshot(settings)
    second_snapshot_id = service.store_runtime_snapshot(settings.model_copy(deep=True))

    assert first_snapshot_id == second_snapshot_id
    assert service.load_runtime_snapshot(first_snapshot_id) == settings
    assert sorted(path.name for path in service.snapshots_dir.glob("*.json")) == [f"{first_snapshot_id}.json"]


def test_runtime_settings_service_publishes_runtime_snapshot_via_atomic_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = RuntimeSettingsService(
        settings_path=tmp_path / "tmp" / "runtime-settings" / "llm-settings.json",
        snapshots_dir=tmp_path / "tmp" / "runtime-settings" / "snapshots",
    )
    settings = EffectiveLLMSettings(
        provider="openai",
        base_url="https://snapshot.example/v1",
        api_key="sk-snapshot-secret-1234",
        model="gpt-snapshot",
        timeout_sec=20,
    )
    replace_calls: list[tuple[str, str]] = []
    original_replace = os.replace

    def tracking_replace(src: str, dst: str) -> None:
        replace_calls.append((src, dst))
        assert Path(src).exists()
        assert Path(src).read_text(encoding="utf-8").strip()
        assert Path(src).name != Path(dst).name
        original_replace(src, dst)

    monkeypatch.setattr(os, "replace", tracking_replace)

    snapshot_id = service.store_runtime_snapshot(settings)

    assert len(replace_calls) == 1
    assert Path(replace_calls[0][1]) == service.snapshots_dir / f"{snapshot_id}.json"
    assert service.load_runtime_snapshot(snapshot_id) == settings


def test_runtime_settings_service_load_runtime_snapshot_rejects_invalid_id_and_corrupt_file(tmp_path: Path) -> None:
    service = RuntimeSettingsService(
        settings_path=tmp_path / "tmp" / "runtime-settings" / "llm-settings.json",
        snapshots_dir=tmp_path / "tmp" / "runtime-settings" / "snapshots",
    )
    service.snapshots_dir.mkdir(parents=True, exist_ok=True)
    invalid_snapshot_id = "../not-a-snapshot"
    corrupt_snapshot_id = "a" * 64
    (service.snapshots_dir / f"{corrupt_snapshot_id}.json").write_text("{not-json", encoding="utf-8")

    assert service.load_runtime_snapshot(invalid_snapshot_id) is None
    assert service.load_runtime_snapshot("xyz") is None
    assert service.load_runtime_snapshot(corrupt_snapshot_id) is None


@pytest.mark.parametrize("settings_cls", [PersistedLLMSettings, EffectiveLLMSettings])
def test_llm_settings_provider_rejects_unknown_values(settings_cls: type[PersistedLLMSettings | EffectiveLLMSettings]) -> None:
    with pytest.raises(ValidationError, match="provider"):
        settings_cls(provider="invalid-provider")


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


def test_create_llm_provider_raises_for_explicit_openai_settings_without_api_key() -> None:
    with pytest.raises(RuntimeError, match="api_key is required"):
        create_llm_provider(
            EffectiveLLMSettings(
                provider="openai",
                base_url="https://explicit.example/v1",
                model="gpt-explicit",
                timeout_sec=12,
            )
        )


def test_create_llm_provider_explicit_auto_without_api_key_still_resolves_to_mock() -> None:
    provider = create_llm_provider(
        EffectiveLLMSettings(
            provider="auto",
            model="ignored",
        )
    )

    assert isinstance(provider, MockLLMProvider)
