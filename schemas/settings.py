from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, field_validator


ALLOWED_LLM_PROVIDERS = {"auto", "mock", "openai"}


def _normalize_optional_str(value: object) -> object:
    if value is None or not isinstance(value, str):
        return value
    normalized = value.strip()
    return normalized or None


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def _normalize_provider(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.lower()
    if normalized not in ALLOWED_LLM_PROVIDERS:
        allowed = ", ".join(sorted(ALLOWED_LLM_PROVIDERS))
        raise ValueError(f"provider must be one of: {allowed}")
    return normalized


class PersistedLLMSettings(BaseModel):
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    timeout_sec: Optional[int] = Field(default=None, ge=1)

    @field_validator("provider", "base_url", "api_key", "model", mode="before")
    @classmethod
    def strip_optional_strings(cls, value: object) -> object:
        return _normalize_optional_str(value)

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str | None) -> str | None:
        return _normalize_provider(value)

    def masked_view(self) -> "MaskedLLMSettings":
        return MaskedLLMSettings(
            provider=self.provider,
            base_url=self.base_url,
            model=self.model,
            timeout_sec=self.timeout_sec,
            has_api_key=bool(self.api_key),
            api_key_masked=mask_secret(self.api_key),
        )


class MaskedLLMSettings(BaseModel):
    provider: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    timeout_sec: Optional[int] = None
    has_api_key: bool = False
    api_key_masked: Optional[str] = None


class EffectiveLLMSettings(BaseModel):
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    timeout_sec: Optional[int] = Field(default=None, ge=1)

    @field_validator("provider", "base_url", "api_key", "model", mode="before")
    @classmethod
    def strip_optional_strings(cls, value: object) -> object:
        return _normalize_optional_str(value)

    @field_validator("provider")
    @classmethod
    def normalize_provider(cls, value: str | None) -> str | None:
        return _normalize_provider(value)
