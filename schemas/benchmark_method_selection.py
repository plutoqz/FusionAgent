from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProjectionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    condition_id: Literal[
        "fixed_workflow",
        "rules_only",
        "kg_only",
        "llm_only",
        "llm_capability_kg",
        "llm_full_contract_kg",
    ]
    visible_fields: tuple[str, ...] = Field(min_length=1)
    forbidden_fields: tuple[str, ...] = Field(min_length=1)
    projection_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    def __init__(self, **data):
        super().__init__(**data)
        if set(self.visible_fields) & set(self.forbidden_fields):
            raise ValueError("visible and forbidden fields must be disjoint")


class MethodIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    method_id: Literal["llm_only", "llm_capability_kg", "llm_full_contract_kg"]
    method_commit: str = Field(min_length=1)
    kg_release_id: str = Field(min_length=1)
    kg_semantic_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    projection_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    prompt_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    schema_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    selection_protocol_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
