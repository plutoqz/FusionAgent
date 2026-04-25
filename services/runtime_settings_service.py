from __future__ import annotations

import json
import os
from pathlib import Path

from schemas.settings import EffectiveLLMSettings, MaskedLLMSettings, PersistedLLMSettings


DEFAULT_RUNTIME_SETTINGS_PATH = Path("tmp/runtime-settings/llm-settings.json")


class RuntimeSettingsService:
    def __init__(self, settings_path: Path | None = None) -> None:
        self.settings_path = settings_path or DEFAULT_RUNTIME_SETTINGS_PATH

    def save_llm_settings(self, settings: PersistedLLMSettings) -> MaskedLLMSettings:
        persisted = PersistedLLMSettings.model_validate(settings)
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        self.settings_path.write_text(
            json.dumps(persisted.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return persisted.masked_view()

    def get_llm_settings(self) -> MaskedLLMSettings:
        return self._load_persisted_settings().masked_view()

    def get_effective_llm_settings(self) -> EffectiveLLMSettings:
        persisted = self._load_persisted_settings()
        return EffectiveLLMSettings(
            provider=self._read_env_value("GEOFUSION_LLM_PROVIDER") or persisted.provider,
            base_url=self._read_env_value("GEOFUSION_LLM_BASE_URL") or persisted.base_url,
            api_key=self._read_api_key() or persisted.api_key,
            model=self._read_env_value("GEOFUSION_LLM_MODEL") or persisted.model,
            timeout_sec=self._read_env_int("GEOFUSION_LLM_TIMEOUT_SEC", persisted.timeout_sec),
        )

    def _load_persisted_settings(self) -> PersistedLLMSettings:
        if not self.settings_path.exists():
            return PersistedLLMSettings()
        raw = self.settings_path.read_text(encoding="utf-8").strip()
        if not raw:
            return PersistedLLMSettings()
        return PersistedLLMSettings.model_validate(json.loads(raw))

    @staticmethod
    def _read_env_value(name: str) -> str | None:
        value = os.getenv(name)
        if value is None:
            return None
        value = value.strip()
        return value or None

    @classmethod
    def _read_api_key(cls) -> str | None:
        return cls._read_env_value("OPENAI_API_KEY") or cls._read_env_value("GEOFUSION_LLM_API_KEY")

    @classmethod
    def _read_env_int(cls, name: str, default: int | None) -> int | None:
        raw = cls._read_env_value(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            return default
