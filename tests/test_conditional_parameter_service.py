from __future__ import annotations

from kg.models import AlgorithmParameterSpec
from services.conditional_parameter_service import (
    ConditionalParameterContext,
    resolve_effective_parameters,
)


def _spec() -> AlgorithmParameterSpec:
    return AlgorithmParameterSpec(
        spec_id="ps.algo.fusion.building.v1.match_similarity_threshold",
        algo_id="algo.fusion.building.v1",
        key="match_similarity_threshold",
        label="Match Similarity Threshold",
        param_type="float",
        default=0.70,
        min_value=0.0,
        max_value=1.0,
        conditional_defaults=[
            {
                "when": {"source_combination": ["raw.google.building", "raw.osm.building"]},
                "value": 0.75,
                "provenance": {"source": "manual_seed"},
            },
            {
                "when": {"region_country_name": "Nepal"},
                "value": 0.65,
                "provenance": {"source": "operator_annotation"},
            },
        ],
        default_provenance={"source": "static_seed"},
    )


def test_source_combination_conditional_default_wins_before_region() -> None:
    context = ConditionalParameterContext(
        source_ids=["raw.google.building", "raw.osm.building"],
        region_country_name="Nepal",
    )

    result = resolve_effective_parameters([_spec()], context)

    assert result.values["match_similarity_threshold"] == 0.75
    assert result.provenance["match_similarity_threshold"]["source"] == "manual_seed"


def test_region_conditional_default_applies_when_source_condition_absent() -> None:
    context = ConditionalParameterContext(
        source_ids=["raw.osm.building", "raw.microsoft.building"],
        region_country_name="Nepal",
    )

    result = resolve_effective_parameters([_spec()], context)

    assert result.values["match_similarity_threshold"] == 0.65
    assert result.provenance["match_similarity_threshold"]["source"] == "operator_annotation"


def test_static_default_has_static_provenance() -> None:
    context = ConditionalParameterContext(source_ids=["raw.osm.building"])

    result = resolve_effective_parameters([_spec()], context)

    assert result.values["match_similarity_threshold"] == 0.70
    assert result.provenance["match_similarity_threshold"]["source"] == "static_seed"


def test_durable_learning_overrides_seeded_or_conditional_default() -> None:
    context = ConditionalParameterContext(
        source_ids=["raw.google.building", "raw.osm.building"],
        region_country_name="Nepal",
        durable_learning_overrides={"match_similarity_threshold": 0.82},
    )

    result = resolve_effective_parameters([_spec()], context)

    assert result.values["match_similarity_threshold"] == 0.82
    assert result.provenance["match_similarity_threshold"]["source"] == "durable_learning"


def test_conditional_default_missing_provenance_uses_conditional_default_source() -> None:
    spec = AlgorithmParameterSpec(
        spec_id="ps.algo.fusion.building.v1.match_similarity_threshold",
        algo_id="algo.fusion.building.v1",
        key="match_similarity_threshold",
        label="Match Similarity Threshold",
        param_type="float",
        default=0.70,
        conditional_defaults=[
            {
                "when": {"region_country_name": "Nepal"},
                "value": 0.65,
            }
        ],
        default_provenance={"source": "static_seed"},
    )
    context = ConditionalParameterContext(region_country_name="Nepal")

    result = resolve_effective_parameters([spec], context)

    assert result.values["match_similarity_threshold"] == 0.65
    assert result.provenance["match_similarity_threshold"]["source"] == "conditional_default"
