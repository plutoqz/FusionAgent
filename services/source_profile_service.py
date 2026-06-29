from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import pyogrio

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


@dataclass(frozen=True)
class _BeninSourceSpec:
    source_id: str
    source_name: str
    source_form: str
    runtime_status: str
    selectable_now: bool
    path_patterns: tuple[str, ...]
    required: bool = True


_BENIN_SOURCE_SPECS: tuple[_BeninSourceSpec, ...] = (
    _BeninSourceSpec(
        source_id="raw.osm.building",
        source_name="OpenStreetMap Building Footprints",
        source_form="vector",
        runtime_status="runtime_candidate",
        selectable_now=True,
        path_patterns=("final_shp/openstreetmap/*.shp",),
    ),
    _BeninSourceSpec(
        source_id="raw.openbuildingmap.building",
        source_name="OpenBuildingMap Building Footprints",
        source_form="vector",
        runtime_status="reservation_only",
        selectable_now=False,
        path_patterns=("final_shp/openbuildingmap/*.shp",),
    ),
    _BeninSourceSpec(
        source_id="raw.google.open_buildings.vector",
        source_name="Google Open Buildings Vector",
        source_form="vector",
        runtime_status="reservation_only",
        selectable_now=False,
        path_patterns=("final_shp/google_open_buildings_v3/*.shp",),
    ),
    _BeninSourceSpec(
        source_id="raw.local.microsoft.building",
        source_name="Local Microsoft Building Footprints",
        source_form="vector",
        runtime_status="reservation_only",
        selectable_now=False,
        path_patterns=("final_shp/microsoft_global_ml_building_footprints/*.shp",),
    ),
    _BeninSourceSpec(
        source_id="raw.google.building_presence.raster",
        source_name="Google Building Presence Raster",
        source_form="raster",
        runtime_status="reservation_only",
        selectable_now=False,
        path_patterns=("_processing/google_open_buildings_temporal_2023/building_presence_2023_benin_4m.tif",),
    ),
    _BeninSourceSpec(
        source_id="raw.google.building_height.raster",
        source_name="Google Building Height Raster",
        source_form="raster",
        runtime_status="reservation_only",
        selectable_now=False,
        path_patterns=("_processing/google_open_buildings_temporal_2023/building_height_2023_benin_4m.tif",),
        required=False,
    ),
)


class SourceProfileService:
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
        metadata: dict[str, Any] | None = None,
    ) -> SourceProfile:
        vector_path = Path(path)
        resolved_feature_count = feature_count
        resolved_crs = crs
        resolved_field_names = list(field_names or [])

        if resolved_feature_count is None or resolved_crs is None or not resolved_field_names:
            info = pyogrio.read_info(vector_path)
            resolved_feature_count = int(info["features"]) if resolved_feature_count is None else resolved_feature_count
            resolved_crs = str(info["crs"]) if resolved_crs is None else resolved_crs
            if not resolved_field_names:
                resolved_field_names = [str(item) for item in list(info["fields"])]

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
        for spec in _BENIN_SOURCE_SPECS:
            matches = self._resolve_matches(base, spec.path_patterns)
            if not matches and not spec.required:
                continue
            if spec.source_form == "vector":
                profile = self._profile_vector_candidates(spec, matches)
            else:
                profile = self._profile_raster_candidates(spec, matches)
            profiles.append(profile)
        return {"profiles": [item.to_dict() for item in profiles]}

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
