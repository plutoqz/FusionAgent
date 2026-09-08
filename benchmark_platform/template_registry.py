from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from benchmark_platform.canonical import canonical_sha256
from benchmark_platform.models import BenchmarkPlatformValidationError, FailureClass, FailureRecord
from benchmark_platform.template_authoring import TemplateFamilyContract


class TemplateRegistryError(BenchmarkPlatformValidationError):
    pass


class TemplateRegistryAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    template_count: int = Field(ge=0)
    unique_family_ids: int = Field(ge=0)
    coverage_tags: tuple[str, ...]
    complexity_levels: tuple[str, ...]
    semantic_signatures: tuple[str, ...]
    duplicate_family_ids: tuple[str, ...]
    duplicate_semantic_signatures: tuple[str, ...]
    missing_required_tags: tuple[str, ...]
    passed: bool
    registry_hash: str


REQUIRED_COVERAGE_TAGS = ("building", "road", "water_polygon", "waterways", "poi", "gap", "veto", "delivery", "recovery")


def _fail(code: str, message: str) -> None:
    raise TemplateRegistryError([
        FailureRecord(failure_class=FailureClass.RUNTIME_INVALID_STATE, message=message, validator="template_registry", details={"code": code})
    ])


def audit_template_registry(
    contracts: tuple[TemplateFamilyContract, ...],
    templates: tuple[Mapping[str, Any], ...],
    *,
    min_families: int = 10,
    max_families: int = 15,
) -> TemplateRegistryAudit:
    if len(contracts) != len(templates):
        _fail("length_mismatch", "each template must have exactly one authoring contract")
    if not min_families <= len(contracts) <= max_families:
        _fail("family_count", f"template registry must contain {min_families}-{max_families} families")
    family_ids = [item.template_family_id for item in contracts]
    duplicate_ids = tuple(sorted({item for item in family_ids if family_ids.count(item) > 1}))
    signatures = [canonical_sha256({"product_types": sorted(item.effective_product_types), "coverage_tags": sorted(item.coverage_tags), "causal": list(item.causal_variable_ids), "invariant": list(item.invariant_variable_ids), "nuisance": list(item.nuisance_variable_ids)}) for item in contracts]
    duplicate_signatures = tuple(sorted({item for item in signatures if signatures.count(item) > 1}))
    tags = tuple(sorted({tag for item in contracts for tag in item.coverage_tags}))
    missing = tuple(sorted(set(REQUIRED_COVERAGE_TAGS) - set(tags)))
    if duplicate_ids:
        _fail("duplicate_family_id", f"duplicate template family IDs: {', '.join(duplicate_ids)}")
    if duplicate_signatures:
        _fail("semantic_copy", "semantic-equivalent template families are not allowed in one registry")
    if missing:
        _fail("coverage_incomplete", f"required coverage tags are missing: {', '.join(missing)}")
    if any(item.partition != "development" or not item.historical_exclusion_checked for item in contracts):
        _fail("authoring_contract_incomplete", "all template contracts must be development-only and exclusion-checked")
    payload = {
        "family_ids": family_ids,
        "template_hashes": [canonical_sha256(template) for template in templates],
        "contract_hashes": [canonical_sha256(contract.model_dump(mode="json")) for contract in contracts],
        "signatures": signatures,
        "coverage_tags": list(tags),
    }
    return TemplateRegistryAudit(template_count=len(templates), unique_family_ids=len(set(family_ids)), coverage_tags=tags, complexity_levels=tuple(sorted({item.complexity_level for item in contracts})), semantic_signatures=tuple(signatures), duplicate_family_ids=duplicate_ids, duplicate_semantic_signatures=duplicate_signatures, missing_required_tags=missing, passed=True, registry_hash=canonical_sha256(payload))
