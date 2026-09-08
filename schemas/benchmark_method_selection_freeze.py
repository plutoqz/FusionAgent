from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class MethodSelectionFreezeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: Literal["fusionagent.method-selection-freeze-candidate.v1"]
    status: Literal["awaiting_independent_review", "approved"]
    protocol_id: str = Field(min_length=1)
    implementation_branch: str = Field(min_length=1)
    implementation_files: tuple[str, ...] = Field(min_length=1)
    implementation_hashes: dict[str, str] = Field(min_length=1)
    tests_passed: int = Field(ge=1)
    provider_calls: int = Field(ge=0)
    judge_calls: int = Field(ge=0)
    formal_result_roots_created: int = Field(ge=0)
    confirmation_unsealed: bool
    e2e_selected: bool
    unresolved_review_items: tuple[str, ...] = ()
