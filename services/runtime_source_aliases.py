"""Runtime adapter bindings derived from the frozen KG policy release."""

from __future__ import annotations

from pathlib import Path

from kg.policy_registry import default_policy_registry
from kg.seed_provider import load_seed_data


_REGISTRY = default_policy_registry()
_ALIASES = _REGISTRY.source_runtime_aliases()
_SOURCES = {source.source_id: source for source in load_seed_data()["data_sources"]}


def _aliases_for_themes(*themes: str) -> dict[str, str]:
    accepted = set(themes)
    aliases = {
        source_id: alias
        for source_id, alias in _ALIASES.items()
        if source_id in _SOURCES and str((_SOURCES[source_id].metadata or {}).get("theme") or "") in accepted
    }
    for source_id, canonical_id in _REGISTRY.source_id_aliases().items():
        if canonical_id in aliases:
            aliases[source_id] = aliases[canonical_id]
    return aliases


def _alias_priority(binding_id: str) -> tuple[str, ...]:
    source_ids = _REGISTRY.source_priority_order(binding_id)
    missing = [source_id for source_id in source_ids if source_id not in _ALIASES]
    if missing:
        raise ValueError(f"KG runtime binding {binding_id} references sources without aliases: {missing}")
    return tuple(_ALIASES[source_id] for source_id in source_ids)


BUILDING_SOURCE_ALIASES = _aliases_for_themes("building")
BUILDING_SOURCE_PRIORITY_ORDER = _alias_priority("building_vector")
BUILDING_HEIGHT_RASTER_PRIORITY_ORDER = tuple(_REGISTRY.source_priority_order("building_height_raster"))
POI_SOURCE_ALIASES = _aliases_for_themes("poi")
POI_SOURCE_PRIORITY_ORDER = _alias_priority("poi_vector")
LINE_SOURCE_ALIASES = _aliases_for_themes("road", "waterways")
POLYGON_WATER_SOURCE_ALIASES = _aliases_for_themes("water")


def alias_paths(component_paths: dict[str, Path], aliases: dict[str, str]) -> dict[str, Path]:
    aliased_paths: dict[str, Path] = {}
    source_ids_by_alias: dict[str, list[str]] = {}
    for source_id, path in component_paths.items():
        alias = aliases.get(source_id)
        if alias is None:
            continue
        if alias in aliased_paths:
            source_ids = [*source_ids_by_alias[alias], source_id]
            raise ValueError(
                f"Duplicate runtime source alias {alias!r} for source ids: {', '.join(source_ids)}"
            )
        aliased_paths[alias] = path
        source_ids_by_alias[alias] = [source_id]
    return aliased_paths
