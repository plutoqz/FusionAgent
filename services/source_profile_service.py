from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pyogrio

from kg.knowledge_release import KnowledgeReleaseError
from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry
from kg.seed_provider import load_seed_data
from utils.raster_cli import gdalinfo_json


@dataclass(frozen=True)
class SourceProfile:
    source_id: str
    canonical_path: str
    source_form: str
    runtime_status: str
    selectable_now: bool
    crs: str | None
    feature_count: int | None
    field_names: list[str] = field(default_factory=list)
    height_fields: list[str] = field(default_factory=list)
    height_semantics: str = "unknown"
    driver: str | None = None
    geometry_type: str | None = None
    provider_fid_available: bool = False
    provider_fid_count: int | None = None
    provider_fid_sha256: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def classify_height_semantics(
    *,
    source_name: str,
    field_names: list[str],
    raster_band_description: str | None,
) -> str:
    lowered_fields = {item.casefold() for item in field_names}
    description = (raster_band_description or "").casefold()
    lowered_name = source_name.casefold()
    if "height" in lowered_fields:
        return "estimated_height"
    if "presence" in description or "presence" in lowered_name:
        return "presence_only"
    if "height" in description or "height" in lowered_name:
        return "estimated_height"
    return "unknown"


def _profile_provider_fids(
    path: Path,
    *,
    driver: str,
    expected_count: int | None,
) -> tuple[bool, int | None, str | None]:
    if driver not in {"ESRI Shapefile", "GPKG"}:
        return False, None, None
    try:
        frame = pyogrio.read_dataframe(
            path,
            columns=[],
            read_geometry=False,
            fid_as_index=True,
        )
    except Exception:  # noqa: BLE001
        return False, None, None
    identifiers = list(frame.index)
    if expected_count is not None and len(identifiers) != int(expected_count):
        return False, len(identifiers), None
    if any(value is None for value in identifiers) or len(set(identifiers)) != len(identifiers):
        return False, len(identifiers), None
    payload = json.dumps(identifiers, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return True, len(identifiers), "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class _BeninSourceSpec:
    source_id: str
    source_name: str
    source_form: str
    runtime_status: str
    selectable_now: bool
    path_patterns: tuple[str, ...]
    required: bool = True


class SourceProfileService:
    def __init__(self, *, policy_registry: KnowledgePolicyRegistry | None = None) -> None:
        self.policy_registry = policy_registry or default_policy_registry()

    def profile_vector_source(
        self,
        *,
        source_id: str,
        path: Path,
        source_name: str | None = None,
        runtime_status: str = "reservation_only",
        selectable_now: bool = False,
        feature_count: int | None = None,
        crs: str | None = None,
        field_names: list[str] | None = None,
        inspect_provider_fids: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> SourceProfile:
        vector_path = Path(path)
        resolved_feature_count = feature_count
        resolved_crs = crs
        resolved_field_names = list(field_names or [])
        info: dict[str, Any] = {}

        if resolved_feature_count is None or resolved_crs is None or not resolved_field_names:
            info = pyogrio.read_info(vector_path)
            resolved_feature_count = int(info["features"]) if resolved_feature_count is None else resolved_feature_count
            resolved_crs = str(info["crs"]) if resolved_crs is None else resolved_crs
            if not resolved_field_names:
                resolved_field_names = [str(item) for item in list(info["fields"])]

        if not info:
            info = pyogrio.read_info(vector_path)
        if inspect_provider_fids:
            fid_available, fid_count, fid_sha256 = _profile_provider_fids(
                vector_path,
                driver=str(info.get("driver") or ""),
                expected_count=resolved_feature_count,
            )
        else:
            fid_available, fid_count, fid_sha256 = False, None, None

        height_fields = [name for name in resolved_field_names if "height" in name.casefold()]
        semantics = classify_height_semantics(
            source_name=source_name or source_id,
            field_names=resolved_field_names,
            raster_band_description=None,
        )
        return SourceProfile(
            source_id=source_id,
            canonical_path=str(vector_path),
            source_form="vector",
            runtime_status=runtime_status,
            selectable_now=selectable_now,
            crs=resolved_crs,
            feature_count=resolved_feature_count,
            field_names=resolved_field_names,
            height_fields=height_fields,
            height_semantics=semantics,
            driver=str(info.get("driver") or "") or None,
            geometry_type=str(info.get("geometry_type") or "") or None,
            provider_fid_available=fid_available,
            provider_fid_count=fid_count,
            provider_fid_sha256=fid_sha256,
            metadata=dict(metadata or {}),
        )

    def profile_raster_source(
        self,
        *,
        source_id: str,
        path: Path,
        source_name: str | None = None,
        runtime_status: str = "reservation_only",
        selectable_now: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> SourceProfile:
        raster_path = Path(path)
        try:
            info = gdalinfo_json(raster_path)
        except (FileNotFoundError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
            source_label = f"{source_name or source_id} {raster_path.name}"
            return SourceProfile(
                source_id=source_id,
                canonical_path=str(raster_path),
                source_form="raster",
                runtime_status=runtime_status,
                selectable_now=selectable_now,
                crs=None,
                feature_count=None,
                field_names=[],
                height_fields=[],
                height_semantics=classify_height_semantics(
                    source_name=source_label,
                    field_names=[],
                    raster_band_description=None,
                ),
                metadata={
                    "profile_degraded": True,
                    "profile_error": f"{type(exc).__name__}: {exc}",
                    **dict(metadata or {}),
                },
            )
        bands = list(info.get("bands") or [])
        band_description = None
        if bands:
            band_description = str((bands[0] or {}).get("description") or "")
        coordinate_system = info.get("coordinateSystem") or {}
        crs = None
        if isinstance(coordinate_system, dict):
            crs = str(coordinate_system.get("wkt") or "").strip() or None
        size = list(info.get("size") or [])
        merged_meta = {
            "band_count": len(bands),
            "size": size,
            **dict(metadata or {}),
        }
        return SourceProfile(
            source_id=source_id,
            canonical_path=str(raster_path),
            source_form="raster",
            runtime_status=runtime_status,
            selectable_now=selectable_now,
            crs=crs,
            feature_count=None,
            field_names=[],
            height_fields=[],
            height_semantics=classify_height_semantics(
                source_name=source_name or source_id,
                field_names=[],
                raster_band_description=band_description,
            ),
            metadata=merged_meta,
        )

    def profile_benin_root(self, root: Path) -> dict[str, object]:
        base = Path(root)
        profiles: list[SourceProfile] = []
        for spec in self._profiling_specs("profile.benin.building.v1"):
            matches = self._resolve_matches(base, spec.path_patterns)
            if not matches and not spec.required:
                continue
            if spec.source_form == "vector":
                profile = self._profile_vector_candidates(spec, matches)
            else:
                profile = self._profile_raster_candidates(spec, matches)
            profiles.append(profile)
        return {"profiles": [item.to_dict() for item in profiles]}

    def _profiling_specs(self, profile_set_id: str) -> tuple[_BeninSourceSpec, ...]:
        policy = self.policy_registry.source_profiling_set(profile_set_id)
        sources_by_id = {
            source.source_id: source
            for source in load_seed_data()["data_sources"]
        }
        specs: list[_BeninSourceSpec] = []
        for binding in policy["sources"]:
            source_id = str(binding.get("source_id") or "").strip()
            source = sources_by_id.get(source_id)
            if source is None:
                raise KnowledgeReleaseError(
                    f"Source profiling set {profile_set_id} references unknown source {source_id!r}"
                )
            metadata = dict(source.metadata or {})
            path_patterns = tuple(str(item) for item in binding.get("path_patterns", []) if str(item))
            source_form = str(metadata.get("source_form") or "").strip()
            runtime_status = str(metadata.get("runtime_status") or "").strip()
            selectable_now = metadata.get("selectable_now")
            if not path_patterns or source_form not in {"vector", "raster"}:
                raise KnowledgeReleaseError(
                    f"Source profiling binding {source_id} lacks path patterns or source form"
                )
            if not runtime_status or not isinstance(selectable_now, bool):
                raise KnowledgeReleaseError(
                    f"Source {source_id} lacks frozen runtime status/selectability metadata"
                )
            specs.append(
                _BeninSourceSpec(
                    source_id=source_id,
                    source_name=source.source_name,
                    source_form=source_form,
                    runtime_status=runtime_status,
                    selectable_now=selectable_now,
                    path_patterns=path_patterns,
                    required=bool(binding.get("required", True)),
                )
            )
        return tuple(specs)

    @staticmethod
    def _resolve_matches(base: Path, patterns: Iterable[str]) -> list[Path]:
        matches: list[Path] = []
        for pattern in patterns:
            matches.extend(sorted(base.glob(pattern)))
        unique: list[Path] = []
        seen: set[str] = set()
        for path in matches:
            key = str(path.resolve())
            if key in seen:
                continue
            seen.add(key)
            unique.append(path)
        return unique

    def _profile_vector_candidates(self, spec: _BeninSourceSpec, matches: list[Path]) -> SourceProfile:
        if not matches:
            raise FileNotFoundError(f"No vector candidate matched for {spec.source_id}")
        inspected = [self.profile_vector_source(
            source_id=spec.source_id,
            source_name=spec.source_name,
            path=path,
            runtime_status=spec.runtime_status,
            selectable_now=spec.selectable_now,
        ) for path in matches]
        canonical = max(
            inspected,
            key=lambda item: (
                -1 if item.feature_count is None else item.feature_count,
                -len(Path(item.canonical_path).name),
                item.canonical_path,
            ),
        )
        rejected = [item.canonical_path for item in inspected if item.canonical_path != canonical.canonical_path]
        metadata = {
            **canonical.metadata,
            "candidate_paths": [item.canonical_path for item in inspected],
            "rejected_candidate_paths": rejected,
        }
        return SourceProfile(
            source_id=canonical.source_id,
            canonical_path=canonical.canonical_path,
            source_form=canonical.source_form,
            runtime_status=canonical.runtime_status,
            selectable_now=canonical.selectable_now,
            crs=canonical.crs,
            feature_count=canonical.feature_count,
            field_names=canonical.field_names,
            height_fields=canonical.height_fields,
            height_semantics=canonical.height_semantics,
            metadata=metadata,
        )

    def _profile_raster_candidates(self, spec: _BeninSourceSpec, matches: list[Path]) -> SourceProfile:
        if not matches:
            raise FileNotFoundError(f"No raster candidate matched for {spec.source_id}")
        raster = self.profile_raster_source(
            source_id=spec.source_id,
            source_name=spec.source_name,
            path=matches[0],
            runtime_status=spec.runtime_status,
            selectable_now=spec.selectable_now,
            metadata={"candidate_paths": [str(path) for path in matches]},
        )
        return raster
