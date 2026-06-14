from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class RuntimeProviderStatus(str, Enum):
    runtime_ready = "runtime_ready"
    requires_external_config = "requires_external_config"
    reservation_only = "reservation_only"
    missing_provider = "missing_provider"


class RuntimeSourceContract(BaseModel):
    source_id: str
    catalog_selectable: bool = False
    raw_vector_supported: bool = False
    input_bundle_supported: bool = False
    status: RuntimeProviderStatus
    reasons: list[str] = Field(default_factory=list)
    required_external_config: list[str] = Field(default_factory=list)
    provider_names: list[str] = Field(default_factory=list)
