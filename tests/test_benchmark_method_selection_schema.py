from __future__ import annotations

import pytest
from pydantic import ValidationError

from schemas.benchmark_method_selection import MethodIdentity, ProjectionSpec


HASH = "sha256:" + "a" * 64


def test_projection_allowlist_is_disjoint_and_strict():
    spec = ProjectionSpec(
        condition_id="llm_capability_kg",
        visible_fields=("request", "capability_projection"),
        forbidden_fields=("gold", "full_contract_projection"),
        projection_hash=HASH,
    )
    assert spec.condition_id == "llm_capability_kg"
    with pytest.raises(ValueError, match="disjoint"):
        ProjectionSpec(
            condition_id="llm_only",
            visible_fields=("request", "gold"),
            forbidden_fields=("gold",),
            projection_hash=HASH,
        )


def test_method_identity_rejects_unknown_condition_or_bad_hash():
    with pytest.raises(ValidationError):
        MethodIdentity(
            method_id="rules_only",
            method_commit="dev",
            kg_release_id="fusionagent-kg-v1.0.0",
            kg_semantic_hash=HASH,
            projection_hash=HASH,
            prompt_hash=HASH,
            schema_hash=HASH,
            selection_protocol_hash=HASH,
        )
