from __future__ import annotations

from fastapi import APIRouter, HTTPException

from llm.factory import create_llm_provider
from schemas.settings import EffectiveLLMSettings, LLMSettingsValidationResponse, MaskedLLMSettings, PersistedLLMSettings
from services.agent_run_service import agent_run_service
from services.runtime_settings_service import RuntimeSettingsService


router = APIRouter(tags=["settings"])
runtime_settings_service = RuntimeSettingsService()


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
    try:
        persisted_settings = runtime_settings_service.preview_persisted_llm_settings(settings)
        runtime_settings = _runtime_settings_from_persisted(persisted_settings)
        _validate_runtime_settings(runtime_settings)
    except (RuntimeError, ValueError) as exc:
        _raise_unprocessable_entity(exc)

    masked_settings = runtime_settings_service.save_llm_settings(settings)
    agent_run_service.refresh_runtime_dependencies(runtime_settings)
    return masked_settings


@router.post("/settings/llm/validate", response_model=LLMSettingsValidationResponse)
async def validate_llm_settings(settings: PersistedLLMSettings) -> LLMSettingsValidationResponse:
    try:
        persisted_settings = runtime_settings_service.preview_persisted_llm_settings(settings)
        runtime_settings = _runtime_settings_from_persisted(persisted_settings)
        _validate_runtime_settings(runtime_settings)
    except (RuntimeError, ValueError) as exc:
        _raise_unprocessable_entity(exc)

    return LLMSettingsValidationResponse(valid=True, settings=persisted_settings.masked_view())
