from __future__ import annotations

import logging
import os

from llm.providers.base import LLMProvider
from llm.providers.mock_provider import MockLLMProvider
from llm.providers.openai_compatible import OpenAICompatibleProvider
from utils.local_runtime import apply_runtime_entrypoint_defaults


def create_llm_provider() -> LLMProvider:
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
