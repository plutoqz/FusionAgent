"""Compatibility views derived from the frozen KG source entities.

The historical Track B APIs remain available to callers, but this module no
longer owns a hand-written source matrix. Every contract below is reconstructed
from ``kg/ontology/v1.0.0/entities.json`` through the canonical seed loader.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, Tuple

from kg.knowledge_release import DEFAULT_POLICIES_PATH
from kg.seed_provider import load_seed_data


@dataclass(frozen=True)
class TrackBSourceContract:
    source_id: str
    theme: str
    role: str
    acquisition_class: str
    format_hint: str
    clip_strategy: str
    field_mapping_profile: str
    license_boundary: str
    runtime_status: str
    notes: str = ""


@dataclass(frozen=True)
class TrackBThemeContract:
    theme: str
    official_remote_source_ids: Tuple[str, ...]
    manual_preload_source_ids: Tuple[str, ...]
    reservation_only_source_ids: Tuple[str, ...]
    current_catalog_source_ids: Tuple[str, ...]
    implementation_goal: str


def _metadata(node: Any) -> dict[str, Any]:
    return dict(getattr(node, "metadata", {}) or {})


def _as_tuple(metadata: dict[str, Any], field: str) -> tuple[str, ...]:
    values = metadata.get(field)
    if not isinstance(values, list):
        raise ValueError(f"Frozen KG catalog metadata must declare list {field}")
    return tuple(str(value) for value in values)


def _catalog_nodes(nodes: Iterable[Any]) -> list[Any]:
    return [node for node in nodes if _metadata(node).get("kind") == "catalog"]


def _single_contract_ref(nodes: Iterable[Any]) -> str:
    refs = {
        str(_metadata(node).get("source_contract_ref") or "").strip()
        for node in nodes
        if str(_metadata(node).get("source_contract_ref") or "").strip()
    }
    if len(refs) != 1:
        raise ValueError(
            "Frozen KG Track B entities must declare exactly one source_contract_ref"
        )
    return next(iter(refs))


def _build_theme_contracts(nodes: list[Any]) -> Dict[str, TrackBThemeContract]:
    contracts: Dict[str, TrackBThemeContract] = {}
    signatures: dict[str, tuple[object, ...]] = {}
    for node in _catalog_nodes(nodes):
        metadata = _metadata(node)
        theme = str(metadata.get("track_b_theme") or "").strip()
        if not theme:
            continue
        contract = TrackBThemeContract(
            theme=theme,
            official_remote_source_ids=_as_tuple(
                metadata, "track_b_official_remote_source_ids"
            ),
            manual_preload_source_ids=_as_tuple(
                metadata, "track_b_manual_preload_source_ids"
            ),
            reservation_only_source_ids=_as_tuple(
                metadata, "track_b_reservation_only_source_ids"
            ),
            current_catalog_source_ids=_as_tuple(
                metadata, "track_b_current_catalog_source_ids"
            ),
            implementation_goal=str(
                metadata.get("track_b_implementation_goal") or ""
            ).strip(),
        )
        signature = (
            contract.official_remote_source_ids,
            contract.manual_preload_source_ids,
            contract.reservation_only_source_ids,
            contract.current_catalog_source_ids,
            contract.implementation_goal,
        )
        if theme in signatures and signatures[theme] != signature:
            raise ValueError(
                f"Frozen KG catalog entities disagree on Track B theme {theme}"
            )
        signatures[theme] = signature
        contracts[theme] = contract
    if not contracts:
        raise ValueError("Frozen KG contains no Track B theme contracts")
    return contracts


def _build_source_contracts(
    nodes: list[Any],
    theme_contracts: Dict[str, TrackBThemeContract],
) -> Dict[str, TrackBSourceContract]:
    nodes_by_id = {str(node.source_id): node for node in nodes}
    source_themes: dict[str, str] = {}
    for theme, contract in theme_contracts.items():
        for source_id in (
            *contract.official_remote_source_ids,
            *contract.manual_preload_source_ids,
            *contract.reservation_only_source_ids,
        ):
            previous = source_themes.setdefault(source_id, theme)
            if previous != theme:
                raise ValueError(
                    f"Frozen KG assigns Track B source {source_id} to multiple themes"
                )
    for source_id, node in nodes_by_id.items():
        metadata = _metadata(node)
        theme = str(metadata.get("track_b_theme") or "").strip()
        if theme and metadata.get("kind") != "catalog":
            source_themes.setdefault(source_id, theme)

    contracts: Dict[str, TrackBSourceContract] = {}
    for source_id, theme in sorted(source_themes.items()):
        node = nodes_by_id.get(source_id)
        if node is None:
            raise ValueError(
                f"Frozen KG Track B theme contract references unknown source {source_id}"
            )
        metadata = _metadata(node)
        contracts[source_id] = TrackBSourceContract(
            source_id=source_id,
            theme=theme,
            role=str(
                metadata.get("track_b_role")
                or metadata.get("source_role")
                or "unspecified"
            ),
            acquisition_class=str(
                metadata.get("acquisition_class") or "unspecified"
            ),
            format_hint=str(metadata.get("format_hint") or ""),
            clip_strategy=str(metadata.get("clip_strategy") or ""),
            field_mapping_profile=str(
                metadata.get("field_mapping_profile") or ""
            ),
            license_boundary=str(metadata.get("license_boundary") or ""),
            runtime_status=str(
                metadata.get("runtime_status") or "reservation_only"
            ),
            notes=str(metadata.get("track_b_notes") or ""),
        )
    return contracts


def _add_source_aliases(
    contracts: Dict[str, TrackBSourceContract],
    aliases: dict[str, str],
) -> None:
    for alias, canonical_id in aliases.items():
        canonical = contracts.get(canonical_id)
        if canonical is None:
            continue
        contracts[alias] = replace(
            canonical,
            source_id=alias,
            role=f"{canonical.role}_alias",
            notes=(
                f"Alias {alias} for GNS / GeoNames source {canonical_id}; "
                "runtime materialization uses the canonical frozen KG source."
            ),
        )


_SEED = load_seed_data()
_DATA_SOURCES = list(_SEED["data_sources"])
TRACK_B_SOURCE_CONTRACT_REF = _single_contract_ref(_DATA_SOURCES)
TRACK_B_THEME_CONTRACTS = _build_theme_contracts(_DATA_SOURCES)
TRACK_B_SOURCE_CONTRACTS = _build_source_contracts(
    _DATA_SOURCES, TRACK_B_THEME_CONTRACTS
)

_add_source_aliases(
    TRACK_B_SOURCE_CONTRACTS,
    {
        str(alias): str(canonical_id)
        for alias, canonical_id in (
            json.loads(DEFAULT_POLICIES_PATH.read_text(encoding="utf-8"))
            .get("source_runtime_bindings", {})
            .get("source_id_aliases", {})
        ).items()
    },
)


def get_track_b_source_contract(source_id: str) -> TrackBSourceContract | None:
    return TRACK_B_SOURCE_CONTRACTS.get(source_id)


def get_track_b_theme_contract(theme: str) -> TrackBThemeContract | None:
    return TRACK_B_THEME_CONTRACTS.get(theme)


def track_b_source_metadata(source_id: str) -> dict[str, object]:
    contract = get_track_b_source_contract(source_id)
    if contract is None:
        return {}
    return {
        "track_b_theme": contract.theme,
        "track_b_role": contract.role,
        "acquisition_class": contract.acquisition_class,
        "format_hint": contract.format_hint,
        "clip_strategy": contract.clip_strategy,
        "field_mapping_profile": contract.field_mapping_profile,
        "license_boundary": contract.license_boundary,
        "source_matrix_stage": "track_b_b1_locked",
        "source_contract_ref": TRACK_B_SOURCE_CONTRACT_REF,
        "track_b_notes": contract.notes,
    }


def track_b_theme_metadata(theme: str) -> dict[str, object]:
    contract = get_track_b_theme_contract(theme)
    if contract is None:
        return {}
    return {
        "track_b_theme": contract.theme,
        "track_b_official_remote_source_ids": list(
            contract.official_remote_source_ids
        ),
        "track_b_manual_preload_source_ids": list(
            contract.manual_preload_source_ids
        ),
        "track_b_reservation_only_source_ids": list(
            contract.reservation_only_source_ids
        ),
        "track_b_current_catalog_source_ids": list(
            contract.current_catalog_source_ids
        ),
        "track_b_implementation_goal": contract.implementation_goal,
        "source_matrix_stage": "track_b_b1_locked",
        "source_contract_ref": TRACK_B_SOURCE_CONTRACT_REF,
    }
