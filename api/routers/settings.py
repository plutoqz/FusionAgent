from __future__ import annotations

from threading import Lock

from fastapi import APIRouter, HTTPException

from llm.factory import create_llm_provider
from schemas.settings import EffectiveLLMSettings, LLMSettingsValidationResponse, MaskedLLMSettings, PersistedLLMSettings
from services.agent_run_service import agent_run_service
from services.runtime_settings_service import RuntimeSettingsService


router = APIRouter(tags=["settings"])
runtime_settings_service = RuntimeSettingsService()
settings_update_lock = Lock()


def probe_llm_settings(llm_settings: EffectiveLLMSettings) -> None:
    return None


def _runtime_settings_from_persisted(settings: PersistedLLMSettings) -> EffectiveLLMSettings:
    return EffectiveLLMSettings(**settings.model_dump(mode="python"))


def _validate_runtime_settings(llm_settings: EffectiveLLMSettings) -> None:
    create_llm_provider(llm_settings)
    probe_llm_settings(llm_settings)


def _raise_unprocessable_entity(exc: Exception) -> None:
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/settings/llm", response_model=MaskedLLMSettings)
async def get_llm_settings() -> MaskedLLMSettings:
    return runtime_settings_service.get_llm_settings()


@router.put("/settings/llm", response_model=MaskedLLMSettings)
async def update_llm_settings(settings: PersistedLLMSettings) -> MaskedLLMSettings:
    with settings_update_lock:
        current_persisted = runtime_settings_service.get_persisted_llm_settings()
        try:
            persisted_settings = runtime_settings_service.merge_persisted_llm_settings(current_persisted, settings)
            runtime_settings = _runtime_settings_from_persisted(persisted_settings)
            _validate_runtime_settings(runtime_settings)
        except (RuntimeError, ValueError) as exc:
            _raise_unprocessable_entity(exc)

        runtime_settings_service.write_persisted_llm_settings(persisted_settings)
        try:
            agent_run_service.refresh_runtime_dependencies(runtime_settings)
        except Exception as exc:  # noqa: BLE001
            runtime_settings_service.write_persisted_llm_settings(current_persisted)
            raise HTTPException(status_code=500, detail=f"Failed to refresh runtime settings: {exc}") from exc

        return persisted_settings.masked_view()


@router.post("/settings/llm/validate", response_model=LLMSettingsValidationResponse)
async def validate_llm_settings(settings: PersistedLLMSettings) -> LLMSettingsValidationResponse:
    try:
        persisted_settings = runtime_settings_service.preview_persisted_llm_settings(settings)
        runtime_settings = _runtime_settings_from_persisted(persisted_settings)
        _validate_runtime_settings(runtime_settings)
    except (RuntimeError, ValueError) as exc:
        _raise_unprocessable_entity(exc)

    return LLMSettingsValidationResponse(valid=True, settings=persisted_settings.masked_view())
