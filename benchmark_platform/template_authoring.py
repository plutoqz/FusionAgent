from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from benchmark_platform.crosswalk import validate_crosswalk
from benchmark_platform.design_loader import FrozenDesignBundle
from benchmark_platform.models import BenchmarkPlatformValidationError, FailureClass, FailureRecord, validate_template_document


class TemplateAuthoringError(BenchmarkPlatformValidationError):
    pass


class TemplateFamilyContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    template_family_id: str = Field(pattern=r"^TF-[A-Z0-9-]+$")
    status: str = Field(default="v1_ready", pattern=r"^(v1_ready|v2_candidate)$")
    product_type: str | None = None
    product_types: tuple[str, ...] = ()
    complexity_level: str = Field(pattern=r"^L[0-4]$")
    claim_ids: tuple[str, ...] = ()
    capability_cell_ids: tuple[str, ...] = ()
    mechanism_family: str = ""
    experiment_unit_type: str = ""
    coverage_tags: tuple[str, ...] = Field(min_length=1)
    causal_variable_ids: tuple[str, ...]
    invariant_variable_ids: tuple[str, ...]
    nuisance_variable_ids: tuple[str, ...]
    contract_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    algorithm_ids: tuple[str, ...] = ()
    quality_policy_ids: tuple[str, ...] = ()
    other_policy_ids: tuple[str, ...] = ()
    required_v2_extensions: tuple[str, ...] = ()
    partition: str = "development"
    historical_exclusion_checked: bool

    @property
    def effective_product_types(self) -> tuple[str, ...]:
        return self.product_types or ((self.product_type,) if self.product_type else ())


class TemplateAuthoringAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    template_family_id: str
    contract: TemplateFamilyContract
    schema_valid: bool
    crosswalk_valid: bool
    oracle_present: bool
    veto_present: bool
    historical_ids_found: tuple[str, ...]
    passed: bool


def _fail(code: str, message: str) -> None:
    raise TemplateAuthoringError([
        FailureRecord(failure_class=FailureClass.RUNTIME_INVALID_STATE, message=message, validator="template_authoring", details={"code": code})
    ])


def audit_template_family(bundle: FrozenDesignBundle, template: Mapping[str, Any], contract: TemplateFamilyContract) -> TemplateAuthoringAudit:
    if contract.partition != "development":
        _fail("invalid_partition", "template authoring is restricted to development")
    if contract.template_family_id != template.get("template_family_id"):
        _fail("identity_mismatch", "authoring contract and template family ID differ")
    exact_fields = {
        "complexity_level": contract.complexity_level,
        "mechanism_family": contract.mechanism_family,
    }
    for field, expected in exact_fields.items():
        if not expected:
            continue
        if template.get(field) != expected:
            _fail("contract_mismatch", f"template {field} differs from its authoring contract")
    sequence_fields = {
        "claim_ids": contract.claim_ids,
        "capability_cell_ids": contract.capability_cell_ids,
    }
    for field, expected in sequence_fields.items():
        if not expected:
            continue
        if tuple(template.get(field, ())) != expected:
            _fail("contract_mismatch", f"template {field} differs from its authoring contract")
    task_kinds = tuple(sorted({str(item.get("task_kind")) for item in template.get("task_state", {}).get("tasks", []) if isinstance(item, Mapping)}))
    if contract.effective_product_types and task_kinds != tuple(sorted(contract.effective_product_types)):
        _fail("product_scope_mismatch", "template task kinds differ from the approved product types")
    historical = set(bundle.selection.get("historical_exclusion", {}).get("case_ids", []))
    inspected = deepcopy(dict(template))
    # The exclusion registry itself legitimately contains historical IDs; inspect authored semantics only.
    partition = inspected.get("partition_policy")
    if isinstance(partition, dict):
        partition.pop("historical_case_ids_forbidden_in_confirmation", None)
    text = str(inspected)
    found = tuple(sorted(item for item in historical if item in text))
    if found or not contract.historical_exclusion_checked:
        _fail("historical_overlap", "historical case IDs or unacknowledged exclusion policy found")
    try:
        validate_template_document(template, bundle.schema_document)
        schema_valid = True
    except BenchmarkPlatformValidationError as error:
        _fail("schema_invalid", "template does not satisfy the frozen template schema")
    try:
        validate_crosswalk(bundle, template)
        crosswalk_valid = True
    except BenchmarkPlatformValidationError as error:
        _fail("crosswalk_invalid", "template crosswalk is not closed against KG v1")
    variables = template.get("variables", {})
    causal = tuple(str(item.get("variable_id")) for item in variables.get("causal_variables", []) if isinstance(item, Mapping))
    invariant = tuple(str(item.get("variable_id")) for item in variables.get("invariants", []) if isinstance(item, Mapping))
    nuisance = tuple(str(item.get("variable_id")) for item in variables.get("nuisance_variables", []) if isinstance(item, Mapping))
    if causal != contract.causal_variable_ids or invariant != contract.invariant_variable_ids or nuisance != contract.nuisance_variable_ids:
        _fail("variable_role_mismatch", "authoring contract variable roles do not match template")
    if contract.experiment_unit_type and template.get("experiment_unit", {}).get("unit_type") != contract.experiment_unit_type:
        _fail("contract_mismatch", "template experiment unit differs from its authoring contract")
    oracle_present = isinstance(template.get("oracle"), Mapping) and bool(template["oracle"].get("allowed_decisions"))
    veto_present = isinstance(template.get("vetoes"), list) and bool(template["vetoes"])
    passed = schema_valid and crosswalk_valid and oracle_present and veto_present and bool(contract.coverage_tags)
    return TemplateAuthoringAudit(template_family_id=contract.template_family_id, contract=contract, schema_valid=schema_valid, crosswalk_valid=crosswalk_valid, oracle_present=oracle_present, veto_present=veto_present, historical_ids_found=found, passed=passed)
