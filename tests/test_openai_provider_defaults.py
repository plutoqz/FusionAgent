from __future__ import annotations

from llm.providers.openai_compatible import OpenAICompatibleProvider


def test_openai_provider_from_env_defaults_to_gpt_5_4_mini(monkeypatch) -> None:
    monkeypatch.setenv("GEOFUSION_LLM_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEOFUSION_LLM_MODEL", raising=False)
    monkeypatch.delenv("GEOFUSION_LLM_BASE_URL", raising=False)

    provider = OpenAICompatibleProvider.from_env()

    assert provider.model == "gpt-5.4-mini"
    assert provider.base_url == "https://api.openai.com/v1"
