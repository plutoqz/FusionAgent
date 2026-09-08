from __future__ import annotations

import pytest

from benchmark_platform.template_authoring import TemplateFamilyContract
from benchmark_platform.template_registry import TemplateRegistryError, audit_template_registry


def _contract(index: int, tag: str) -> TemplateFamilyContract:
    return TemplateFamilyContract(template_family_id=f"TF-REG-{index:02d}", product_type=tag, complexity_level="L1", coverage_tags=(tag, "gap", "veto", "delivery", "recovery"), causal_variable_ids=(f"VAR-{index}",), invariant_variable_ids=(), nuisance_variable_ids=(), historical_exclusion_checked=True)


def test_registry_requires_10_to_15_semantically_distinct_families_and_full_coverage():
    tags = ("building", "road", "water_polygon", "waterways", "poi", "building", "road", "water_polygon", "waterways", "poi")
    contracts = tuple(_contract(i, tag) for i, tag in enumerate(tags))
    result = audit_template_registry(contracts, tuple({"template_family_id": item.template_family_id} for item in contracts))
    assert result.passed is True
    assert result.template_count == 10
    assert result.registry_hash.startswith("sha256:")


def test_registry_rejects_short_or_semantic_duplicate_registry():
    with pytest.raises(TemplateRegistryError, match="10-15"):
        audit_template_registry((_contract(1, "building"),), ({},))
    first = _contract(1, "building")
    second = first.model_copy(update={"template_family_id": "TF-REG-02"})
    with pytest.raises(TemplateRegistryError, match="semantic-equivalent"):
        audit_template_registry((first, second), ({}, {}), min_families=2, max_families=2)
