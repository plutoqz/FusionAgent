from __future__ import annotations

import logging
import os

from llm.providers.base import LLMProvider
from llm.providers.mock_provider import MockLLMProvider
from llm.providers.openai_compatible import OpenAICompatibleProvider
from schemas.settings import EffectiveLLMSettings
from utils.local_runtime import apply_runtime_entrypoint_defaults


def create_llm_provider(settings: EffectiveLLMSettings | None = None) -> LLMProvider:
    if settings is not None:
        return _create_llm_provider_from_settings(settings)
    return _create_llm_provider_from_env()


def _create_llm_provider_from_env() -> LLMProvider:
    apply_runtime_entrypoint_defaults()
    provider_name = os.getenv("GEOFUSION_LLM_PROVIDER", "").strip().lower()
    logger = logging.getLogger("geofusion.llm")

    if provider_name in {"", "auto"}:
        if os.getenv("OPENAI_API_KEY") or os.getenv("GEOFUSION_LLM_API_KEY"):
            provider_name = "openai"
        else:
            provider_name = "mock"

    if provider_name == "openai":
        try:
            provider = OpenAICompatibleProvider.from_env()
            logger.info("LLM provider: openai-compatible")
            return provider
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to initialize openai provider (%s); fallback to mock", exc)
            return MockLLMProvider()

    if provider_name == "mock":
        logger.info("LLM provider: mock")
        return MockLLMProvider()

    logger.warning("Unknown LLM provider '%s'; fallback to mock", provider_name)
    return MockLLMProvider()


def _create_llm_provider_from_settings(settings: EffectiveLLMSettings) -> LLMProvider:
    provider_name = (settings.provider or "").strip().lower()
    logger = logging.getLogger("geofusion.llm")

    if provider_name in {"", "auto"}:
        provider_name = "openai" if settings.api_key else "mock"

    if provider_name == "openai":
        if not settings.api_key:
            raise RuntimeError("api_key is required for openai provider.")
        provider = OpenAICompatibleProvider(
            api_key=settings.api_key,
            model=settings.model or "gpt-5.4-mini",
            base_url=settings.base_url or "https://api.openai.com/v1",
            timeout_sec=settings.timeout_sec or 60,
        )
        logger.info("LLM provider: openai-compatible")
        return provider

    if provider_name == "mock":
        logger.info("LLM provider: mock")
        return MockLLMProvider()

    raise ValueError(f"Unknown LLM provider '{provider_name}'.")
