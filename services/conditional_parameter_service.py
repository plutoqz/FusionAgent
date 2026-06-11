from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from kg.models import AlgorithmParameterSpec


@dataclass(frozen=True)
class ConditionalParameterContext:
    source_ids: list[str] = field(default_factory=list)
    region_country_name: str | None = None
    region_country_code: str | None = None
    aoi_size_bucket: str | None = None
    quality_outcome: str | None = None
    durable_learning_overrides: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EffectiveParameterResult:
    values: dict[str, Any]
    provenance: dict[str, dict[str, Any]]


def resolve_effective_parameters(
    specs: Iterable[AlgorithmParameterSpec],
    context: ConditionalParameterContext,
) -> EffectiveParameterResult:
    values: dict[str, Any] = {}
    provenance: dict[str, dict[str, Any]] = {}
    durable_overrides = dict(context.durable_learning_overrides or {})

    for spec in specs:
        key = getattr(spec, "key", None)
        if not key:
            continue

        value = getattr(spec, "default", None)
        source = _provenance_or_static_seed(getattr(spec, "default_provenance", None))

        for candidate in getattr(spec, "conditional_defaults", []) or []:
            if not isinstance(candidate, dict):
                continue
            if _matches_condition(candidate.get("when") or {}, context):
                value = candidate.get("value")
                source = _provenance_or_static_seed(candidate.get("provenance"))
                break

        if key in durable_overrides:
            value = durable_overrides[key]
            source = {"source": "durable_learning"}

        values[str(key)] = value
        provenance[str(key)] = source

    return EffectiveParameterResult(values=values, provenance=provenance)


def _matches_condition(condition: dict[str, Any], context: ConditionalParameterContext) -> bool:
    if not isinstance(condition, dict) or not condition:
        return False

    supported_keys = {
        "source_combination",
        "region_country_name",
        "region_country_code",
        "aoi_size_bucket",
        "quality_outcome",
    }
    if any(key not in supported_keys for key in condition):
        return False

    if "source_combination" in condition:
        required_sources = _as_string_set(condition["source_combination"])
        context_sources = {str(source_id) for source_id in context.source_ids}
        if not required_sources.issubset(context_sources):
            return False

    if "region_country_name" in condition:
        if _casefold(condition["region_country_name"]) != _casefold(context.region_country_name):
            return False

    if "region_country_code" in condition:
        if _casefold(condition["region_country_code"]) != _casefold(context.region_country_code):
            return False

    if "aoi_size_bucket" in condition:
        if str(condition["aoi_size_bucket"]) != str(context.aoi_size_bucket or ""):
            return False

    if "quality_outcome" in condition:
        if str(condition["quality_outcome"]) != str(context.quality_outcome or ""):
            return False

    return True


def _as_string_set(value: Any) -> set[str]:
    if isinstance(value, str):
        return {value}
    try:
        return {str(item) for item in value}
    except TypeError:
        return {str(value)}


def _casefold(value: Any) -> str:
    return str(value or "").casefold()


def _provenance_or_static_seed(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and value:
        return dict(value)
    return {"source": "static_seed"}
