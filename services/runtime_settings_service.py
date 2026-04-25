from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path

from pydantic import ValidationError

from schemas.settings import EffectiveLLMSettings, MaskedLLMSettings, PersistedLLMSettings


DEFAULT_RUNTIME_SETTINGS_PATH = Path("tmp/runtime-settings/llm-settings.json")
DEFAULT_RUNTIME_SNAPSHOTS_DIR = DEFAULT_RUNTIME_SETTINGS_PATH.parent / "snapshots"
SNAPSHOT_ID_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class RuntimeSettingsService:
    def __init__(self, settings_path: Path | None = None, snapshots_dir: Path | None = None) -> None:
        self.settings_path = settings_path or DEFAULT_RUNTIME_SETTINGS_PATH
        self.snapshots_dir = snapshots_dir or DEFAULT_RUNTIME_SNAPSHOTS_DIR

    def save_llm_settings(self, settings: PersistedLLMSettings) -> MaskedLLMSettings:
        persisted = self._merge_persisted_settings_patch(PersistedLLMSettings.model_validate(settings))
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

    def store_runtime_snapshot(self, settings: EffectiveLLMSettings) -> str:
        effective = EffectiveLLMSettings.model_validate(settings)
        serialized = self._serialize_runtime_snapshot(effective)
        snapshot_id = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
        path = self._runtime_snapshot_path(snapshot_id)
        temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            temp_path.write_text(serialized, encoding="utf-8")
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
        return snapshot_id

    def load_runtime_snapshot(self, snapshot_id: str | None) -> EffectiveLLMSettings | None:
        if not self._is_valid_snapshot_id(snapshot_id):
            return None
        path = self._runtime_snapshot_path(snapshot_id)
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8").strip()
            if not raw:
                return None
            return EffectiveLLMSettings.model_validate(json.loads(raw))
        except (OSError, json.JSONDecodeError, ValidationError):
            return None

    def _load_persisted_settings(self) -> PersistedLLMSettings:
        if not self.settings_path.exists():
            return PersistedLLMSettings()
        raw = self.settings_path.read_text(encoding="utf-8").strip()
        if not raw:
            return PersistedLLMSettings()
        return PersistedLLMSettings.model_validate(json.loads(raw))

    def _merge_persisted_settings_patch(self, patch: PersistedLLMSettings) -> PersistedLLMSettings:
        current = self._load_persisted_settings()
        provided_fields = set(patch.model_fields_set)
        if not provided_fields:
            return current

        merged_payload = current.model_dump(mode="python")
        for field_name in provided_fields:
            merged_payload[field_name] = getattr(patch, field_name)
        return PersistedLLMSettings.model_validate(merged_payload)

    def _runtime_snapshot_path(self, snapshot_id: str) -> Path:
        return self.snapshots_dir / f"{snapshot_id}.json"

    @staticmethod
    def _serialize_runtime_snapshot(settings: EffectiveLLMSettings) -> str:
        return json.dumps(
            settings.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _is_valid_snapshot_id(snapshot_id: str | None) -> bool:
        if not snapshot_id:
            return False
        return SNAPSHOT_ID_PATTERN.fullmatch(snapshot_id) is not None

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
