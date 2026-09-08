from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field

from benchmark_platform.context import CanonicalContext
from benchmark_platform.design_loader import FrozenDesignBundle
from benchmark_platform.generator import GenerationRequest, GenerationResult, generate_development
from benchmark_platform.models import BenchmarkPlatformValidationError, FailureClass, FailureRecord
from benchmark_platform.oracle import OracleProof, solve_template_oracle
from benchmark_platform.projections import ConditionProjection, ConditionId, project_condition
from benchmark_platform.relations import RelationValidationReport, validate_relations


class PreflightError(BenchmarkPlatformValidationError):
    pass


class BlindReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    packet_item_id: str
    instance_id: str
    view_payload: dict[str, Any]
    rubric_ids: tuple[str, ...] = Field(min_length=1)


class PreflightResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generation: GenerationResult
    oracle: OracleProof
    relation: RelationValidationReport
    projections: tuple[ConditionProjection, ...] = Field(min_length=6, max_length=6)
    blind_review_items: tuple[BlindReviewItem, ...] = Field(min_length=6, max_length=6)


def _fail(code: str, message: str) -> None:
    raise PreflightError([
        FailureRecord(
            failure_class=FailureClass.RUNTIME_INVALID_STATE,
            message=message,
            validator="method_selection_preflight",
            details={"code": code},
        )
    ])


def run_development_preflight(
    bundle: FrozenDesignBundle,
    template: Mapping[str, Any],
    context: CanonicalContext,
    *,
    capability_cell_id: str,
    unit_index: int = 0,
    request_payload: Mapping[str, Any],
    output_schema: Mapping[str, Any],
    rules: Mapping[str, Any] | None = None,
    workflow_interface: Mapping[str, Any] | None = None,
) -> PreflightResult:
    generation = generate_development(
        bundle,
        template,
        GenerationRequest(
            partition="development",
            capability_cell_id=capability_cell_id,
            unit_index=unit_index,
            seed_namespace="fusionagent-benchmark-v1-development",
            master_seed=2026081901,
        ),
    )
    oracle = solve_template_oracle(template)
    unit = generation.units[0]
    relation = validate_relations(
        unit,
        template,
        "planning.structure_invalid",
        {"planning.structure_invalid", "planning.causal_response", "planning.wording_instability"},
    )
    if not relation.passed:
        _fail("relation_invalid", "development unit failed frozen relation validation")
    conditions: tuple[ConditionId, ...] = (
        "fixed_workflow", "rules_only", "kg_only", "llm_only", "llm_capability_kg", "llm_full_contract_kg"
    )
    projections = tuple(
        project_condition(
            condition,
            context,
            request=request_payload,
            output_schema=output_schema,
            rules=rules,
            workflow_interface=workflow_interface,
            bundle=bundle,
        )
        for condition in conditions
    )
    blind_items = tuple(
        BlindReviewItem(
            packet_item_id=f"blind-{index:03d}",
            instance_id=unit.instance_id,
            view_payload=projection.payload,
            rubric_ids=("contract_satisfaction", "mechanism_response", "evidence_completeness"),
        )
        for index, projection in enumerate(projections, start=1)
    )
    return PreflightResult(
        generation=generation,
        oracle=oracle,
        relation=relation,
        projections=projections,
        blind_review_items=blind_items,
    )
