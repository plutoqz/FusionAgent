"""Compatibility views over source knowledge in the frozen KG release.

The historical catalog API remains available to materializers and adapters, but
it no longer owns source identities, bundle membership, locators, or priority.
Every exported value below is reconstructed from ``entities.json``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import List, Optional, Tuple

from kg.models import DataSourceNode
from kg.seed_provider import load_seed_data


@dataclass(frozen=True)
class CatalogBundleSpec:
    source_id: str
    osm_source_id: str
    ref_source_id: Optional[str]
    bundle_strategy: str

    @property
    def component_source_ids(self) -> Tuple[str, ...]:
        if self.ref_source_id is None:
            return (self.osm_source_id,)
        return (self.osm_source_id, self.ref_source_id)


@dataclass(frozen=True)
class RawVectorSourceSpec:
    source_id: str
    locator_kind: str
    relative_path: Tuple[str, ...]
    glob_pattern: Optional[str] = None

    @property
    def path_hint(self) -> str:
        prefix = "/".join(self.relative_path)
        if self.glob_pattern:
            return f"{prefix}/{self.glob_pattern}" if prefix else self.glob_pattern
        return prefix


def _released_data_sources() -> List[DataSourceNode]:
    return list(load_seed_data()["data_sources"])


def _raw_vector_spec(source: DataSourceNode) -> RawVectorSourceSpec | None:
    metadata = dict(source.metadata or {})
    if metadata.get("kind") != "raw_vector":
        return None
    path_hint = str(metadata.get("path_hint") or "").strip().replace("\\", "/")
    if not path_hint:
        return None
    parts = tuple(part for part in PurePosixPath(path_hint).parts if part not in {"/", "."})
    wildcard_index = next((index for index, part in enumerate(parts) if "*" in part or "?" in part), None)
    if wildcard_index is not None:
        return RawVectorSourceSpec(
            source_id=source.source_id,
            locator_kind="recursive_glob",
            relative_path=parts[:wildcard_index],
            glob_pattern="/".join(parts[wildcard_index:]),
        )
    locator_kind = "exact_path" if PurePosixPath(path_hint).suffix else "first_shp_in_dir"
    return RawVectorSourceSpec(
        source_id=source.source_id,
        locator_kind=locator_kind,
        relative_path=parts,
    )


def _catalog_bundle_spec(source: DataSourceNode) -> CatalogBundleSpec | None:
    metadata = dict(source.metadata or {})
    if metadata.get("kind") != "catalog":
        return None
    component_ids = tuple(str(item) for item in metadata.get("component_source_ids") or [] if item)
    if not component_ids:
        raise ValueError(f"Catalog source {source.source_id} has no component_source_ids in frozen KG release")
    return CatalogBundleSpec(
        source_id=source.source_id,
        osm_source_id=component_ids[0],
        ref_source_id=component_ids[1] if len(component_ids) > 1 else None,
        bundle_strategy=str(metadata.get("bundle_strategy") or "ordered_components"),
    )


_DATA_SOURCES = _released_data_sources()
DEFAULT_DISASTER_TYPES = sorted({item for source in _DATA_SOURCES for item in source.disaster_types})
RAW_VECTOR_SOURCE_SPECS = tuple(
    spec for source in _DATA_SOURCES if (spec := _raw_vector_spec(source)) is not None
)
RAW_VECTOR_SOURCE_SPECS_BY_ID = {spec.source_id: spec for spec in RAW_VECTOR_SOURCE_SPECS}
CATALOG_BUNDLE_SPECS = tuple(
    spec for source in _DATA_SOURCES if (spec := _catalog_bundle_spec(source)) is not None
)
CATALOG_BUNDLE_SPECS_BY_ID = {spec.source_id: spec for spec in CATALOG_BUNDLE_SPECS}


def get_raw_vector_source_spec(source_id: str) -> RawVectorSourceSpec:
    try:
        return RAW_VECTOR_SOURCE_SPECS_BY_ID[source_id]
    except KeyError as exc:
        raise KeyError(f"Unknown raw vector source: {source_id}") from exc


def get_catalog_bundle_spec(source_id: str) -> CatalogBundleSpec:
    try:
        return CATALOG_BUNDLE_SPECS_BY_ID[source_id]
    except KeyError as exc:
        raise KeyError(f"Unknown catalog bundle source: {source_id}") from exc


def build_data_sources() -> List[DataSourceNode]:
    return _released_data_sources()


__all__ = [
    "CATALOG_BUNDLE_SPECS",
    "CATALOG_BUNDLE_SPECS_BY_ID",
    "CatalogBundleSpec",
    "DEFAULT_DISASTER_TYPES",
    "RAW_VECTOR_SOURCE_SPECS",
    "RAW_VECTOR_SOURCE_SPECS_BY_ID",
    "RawVectorSourceSpec",
    "build_data_sources",
    "get_catalog_bundle_spec",
    "get_raw_vector_source_spec",
]
