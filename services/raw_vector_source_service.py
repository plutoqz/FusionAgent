from __future__ import annotations

import hashlib
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import geopandas as gpd

from kg.source_catalog import RAW_VECTOR_SOURCE_SPECS, RawVectorSourceSpec, get_raw_vector_source_spec
from services.aoi_resolution_service import ResolvedAOI
from services.artifact_registry import ArtifactLookupRequest, ArtifactRecord, ArtifactRegistry
from services.source_asset_service import SourceAssetResolution, SourceAssetService, coverage_status_for_count
from utils.crs import normalize_target_crs
from utils.shp_zip import collect_bundle_files, validate_zip_has_shapefile, zip_shapefile_bundle
from utils.vector_clip import (
    BBox,
    REQUEST_BBOX_CRS,
    clip_frame_to_boundary_path,
    clip_frame_to_request_bbox,
    clip_zip_to_boundary_path,
    clip_zip_to_request_bbox,
    frame_bbox_in_crs,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


_LOCAL_VECTOR_GLOB_PATTERNS = ("*.shp", "*.gpkg")


def _local_vector_glob_patterns(pattern: str | None) -> tuple[str, ...]:
    if not pattern:
        return _LOCAL_VECTOR_GLOB_PATTERNS
    patterns = [pattern]
    if pattern.lower().endswith(".shp"):
        patterns.append(f"{pattern[:-4]}.gpkg")
    return tuple(patterns)


def _first_local_vector(directory: Path) -> Path:
    for pattern in _LOCAL_VECTOR_GLOB_PATTERNS:
        matches = sorted(directory.glob(pattern))
        if matches:
            return matches[0]
    raise FileNotFoundError(f"No vector source (.shp/.gpkg) found in {directory}")


def _normalize_path_hint(value: str | None) -> str:
    text = str(value or "").strip().casefold()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _tokenize_path_hint(value: str | None) -> set[str]:
    normalized = _normalize_path_hint(value)
    if not normalized:
        return set()
    return {token for token in normalized.split() if len(token) >= 3}


def _bundle_version_token(vector_path: Path) -> str:
    files = collect_bundle_files(vector_path) if vector_path.suffix.lower() == ".shp" else [vector_path]
    if not files:
        raise FileNotFoundError(f"No vector source files found near {vector_path}")
    payload = "|".join(f"{file.name}:{int(file.stat().st_mtime)}:{file.stat().st_size}" for file in files)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _tile_meta(request_bbox: Optional[BBox]) -> dict[str, object]:
    if request_bbox is None:
        return {
            "tile_scope": "full",
            "tile_bbox": None,
            "tile_key": "full",
        }
    key = hashlib.sha1(repr(tuple(request_bbox)).encode("utf-8")).hexdigest()[:12]
    return {
        "tile_scope": "request_bbox",
        "tile_bbox": [float(value) for value in request_bbox],
        "tile_key": key,
    }


def _clip_meta(resolved_aoi: ResolvedAOI | None) -> dict[str, object]:
    if resolved_aoi is None:
        return {
            "clip_boundary_source_id": None,
            "clip_boundary_artifact_path": None,
            "clip_geometry_hash": None,
            "degraded_bbox_clip": False,
        }
    return {
        "clip_boundary_source_id": resolved_aoi.boundary_source_id,
        "clip_boundary_artifact_path": resolved_aoi.boundary_artifact_path,
        "clip_geometry_hash": resolved_aoi.clip_geometry_hash,
        "degraded_bbox_clip": bool(resolved_aoi.degraded_bbox_clip),
    }


def _has_boundary_clip(resolved_aoi: ResolvedAOI | None) -> bool:
    return bool(resolved_aoi is not None and resolved_aoi.boundary_artifact_path)


def _clip_geometry_hash(resolved_aoi: ResolvedAOI | None) -> str | None:
    return str(resolved_aoi.clip_geometry_hash) if resolved_aoi is not None and resolved_aoi.clip_geometry_hash else None


def _project_source_frame_for_bundle(source_id: str, frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if source_id not in {"raw.overture.transportation", "raw.overture.road"}:
        return frame
    keep_columns = [
        "id",
        "segment_id",
        "road_id",
        "class",
        "subclass",
        "subtype",
        "type",
        "surface",
        "lane_count",
        "lanes",
        "name",
        "names.primary",
        "names_primary",
        "primary_name",
        "ref",
        "geometry",
    ]
    present = [column for column in keep_columns if column in frame.columns]
    if "geometry" not in present and frame.geometry.name in frame.columns:
        present.append(frame.geometry.name)
    return frame[present].copy()


@dataclass(frozen=True)
class MaterializedRawVectorSource:
    zip_path: Path
    bbox: Optional[BBox]
    target_crs: str
    source_id: str
    source_mode: str
    cache_hit: bool
    version_token: str
    feature_count: Optional[int] = None
    coverage_status: str = "unknown"


class RawVectorSourceService:
    def __init__(
        self,
        *,
        root_dir: Path,
        registry: ArtifactRegistry,
        cache_dir: Path,
        source_asset_service: SourceAssetService | None = None,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.registry = registry
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.specs = {spec.source_id: spec for spec in RAW_VECTOR_SOURCE_SPECS}
        self.source_asset_service = source_asset_service or SourceAssetService(
            repo_root=self.root_dir,
            cache_dir=self.cache_dir / "source_assets",
        )

    def can_handle(self, source_id: str) -> bool:
        return source_id in self.specs

    def resolve_local_source_path(
        self,
        source_id: str,
        *,
        resolved_aoi: ResolvedAOI | None = None,
    ) -> Path:
        spec = get_raw_vector_source_spec(source_id)
        return self._resolve_source_path(spec, resolved_aoi=resolved_aoi)

    def current_version(
        self,
        source_id: str,
        *,
        request_bbox: Optional[BBox] = None,
        resolved_aoi: ResolvedAOI | None = None,
    ) -> str:
        resolution = self._resolve_source_resolution(
            source_id,
            request_bbox=request_bbox,
            resolved_aoi=resolved_aoi,
        )
        return resolution.version_token

    def resolve(
        self,
        *,
        source_id: str,
        request_bbox: Optional[BBox],
        target_path: Path,
        target_crs: str,
        resolved_aoi: ResolvedAOI | None = None,
    ) -> MaterializedRawVectorSource:
        normalized_target_crs = normalize_target_crs(target_crs)
        source_resolution = self._resolve_source_resolution(
            source_id,
            request_bbox=request_bbox,
            resolved_aoi=resolved_aoi,
        )
        version_token = source_resolution.version_token
        candidate = self.registry.find_reusable(
            ArtifactLookupRequest(
                required_output_type="dt.raw.vector",
                required_target_crs=normalized_target_crs,
                bbox=None if _has_boundary_clip(resolved_aoi) else request_bbox,
                required_artifact_role="raw_source",
                required_meta={
                    "source_id": source_id,
                    **(
                        {"clip_geometry_hash": _clip_geometry_hash(resolved_aoi)}
                        if _has_boundary_clip(resolved_aoi)
                        else {}
                    ),
                },
            )
        )
        if candidate is not None and candidate.meta.get("source_version") == version_token:
            cache_zip = Path(candidate.artifact_path)
            if _has_boundary_clip(resolved_aoi) and candidate.meta.get("clip_geometry_hash") == _clip_geometry_hash(resolved_aoi):
                copied = self._copy_cached_zip(cache_zip=cache_zip, target_path=target_path)
                feature_count = self._bundle_feature_count(copied)
                return MaterializedRawVectorSource(
                    zip_path=copied,
                    bbox=tuple(candidate.bbox) if candidate.bbox is not None else None,
                    target_crs=normalized_target_crs,
                    source_id=source_id,
                    source_mode="cache_reused",
                    cache_hit=True,
                    version_token=version_token,
                    feature_count=feature_count,
                    coverage_status=coverage_status_for_count(feature_count),
                )
            elif request_bbox is not None and candidate.bbox is not None and tuple(candidate.bbox) != request_bbox:
                clipped = self._clip_cached_zip(
                    cache_zip=cache_zip,
                    request_bbox=request_bbox,
                    target_path=target_path,
                    resolved_aoi=resolved_aoi,
                )
                feature_count = self._bundle_feature_count(clipped)
                return MaterializedRawVectorSource(
                    zip_path=clipped,
                    bbox=request_bbox,
                    target_crs=normalized_target_crs,
                    source_id=source_id,
                    source_mode="clip_reused",
                    cache_hit=True,
                    version_token=version_token,
                    feature_count=feature_count,
                    coverage_status=coverage_status_for_count(feature_count),
                )
            copied = self._copy_cached_zip(cache_zip=cache_zip, target_path=target_path)
            feature_count = self._bundle_feature_count(copied)
            return MaterializedRawVectorSource(
                zip_path=copied,
                bbox=tuple(candidate.bbox) if candidate.bbox is not None else None,
                target_crs=normalized_target_crs,
                source_id=source_id,
                source_mode="cache_reused",
                cache_hit=True,
                version_token=version_token,
                feature_count=feature_count,
                coverage_status=coverage_status_for_count(feature_count),
            )

        cache_zip = self.cache_dir / source_id.replace(".", "_") / version_token / uuid.uuid4().hex / "source.zip"
        materialized = self._materialize_from_source(
            source_id=source_id,
            source_path=source_resolution.path,
            request_bbox=request_bbox,
            target_path=cache_zip,
            target_crs=normalized_target_crs,
            version_token=version_token,
            resolved_aoi=resolved_aoi,
        )
        self.registry.register(
            ArtifactRecord(
                artifact_id=f"raw_vector.{uuid.uuid4().hex}",
                artifact_path=str(cache_zip),
                artifact_role="raw_source",
                job_type="raw_vector",
                created_at=_utc_now(),
                output_data_type="dt.raw.vector",
                target_crs=normalized_target_crs,
                bbox=materialized.bbox,
                meta={
                    "artifact_role": "raw_source",
                    "legacy_artifact_role": "raw_vector",
                    "source_id": source_id,
                    "source_version": version_token,
                    "source_mode": source_resolution.source_mode,
                    **_tile_meta(request_bbox),
                    **_clip_meta(resolved_aoi),
                },
            )
        )
        copied = self._copy_cached_zip(cache_zip=cache_zip, target_path=target_path)
        return MaterializedRawVectorSource(
            zip_path=copied,
            bbox=materialized.bbox,
            target_crs=normalized_target_crs,
            source_id=source_id,
            source_mode="coverage_empty" if (materialized.feature_count or 0) == 0 else "downloaded",
            cache_hit=False,
            version_token=version_token,
            feature_count=materialized.feature_count,
            coverage_status=coverage_status_for_count(materialized.feature_count),
        )

    def _materialize_from_source(
        self,
        *,
        source_id: str,
        source_path: Path,
        request_bbox: Optional[BBox],
        target_path: Path,
        target_crs: str,
        version_token: str,
        resolved_aoi: ResolvedAOI | None = None,
    ) -> MaterializedRawVectorSource:
        gdf = gpd.read_file(source_path)
        if _has_boundary_clip(resolved_aoi):
            clipped = clip_frame_to_boundary_path(
                gdf,
                Path(str(resolved_aoi.boundary_artifact_path)),
                request_bbox=request_bbox,
                request_crs=REQUEST_BBOX_CRS,
            )
        else:
            clipped = clip_frame_to_request_bbox(gdf, request_bbox, request_crs=REQUEST_BBOX_CRS)
        request_space_bbox = frame_bbox_in_crs(clipped, bbox_crs=REQUEST_BBOX_CRS)
        feature_count = len(clipped.index)

        projected = clipped
        if not projected.empty:
            projected = projected.to_crs(target_crs)
        else:
            projected = projected.set_crs(clipped.crs or REQUEST_BBOX_CRS).to_crs(target_crs)
        projected = _project_source_frame_for_bundle(source_id, projected)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        out_dir = target_path.parent / f"bundle_{uuid.uuid4().hex[:8]}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_shp = out_dir / f"{source_path.stem}.shp"
        projected.to_file(out_shp)
        zip_shapefile_bundle(out_shp, target_path)

        return MaterializedRawVectorSource(
            zip_path=target_path,
            bbox=request_space_bbox,
            target_crs=target_crs,
            source_id=source_id,
            source_mode="downloaded",
            cache_hit=False,
            version_token=version_token,
            feature_count=feature_count,
            coverage_status=coverage_status_for_count(feature_count),
        )

    def _resolve_source_resolution(
        self,
        source_id: str,
        *,
        request_bbox: Optional[BBox],
        resolved_aoi: ResolvedAOI | None,
    ) -> SourceAssetResolution:
        if self.source_asset_service.can_materialize(source_id):
            return self.source_asset_service.resolve_raw_source_path(
                source_id,
                request_bbox=request_bbox,
                aoi=resolved_aoi,
            )
        spec = get_raw_vector_source_spec(source_id)
        shp_path = self._resolve_source_path(spec, resolved_aoi=resolved_aoi)
        return SourceAssetResolution(
            source_id=source_id,
            path=shp_path,
            source_mode="local_data",
            cache_hit=True,
            version_token=_bundle_version_token(shp_path),
            bbox=None,
            feature_count=None,
        )

    def _resolve_source_path(
        self,
        spec: RawVectorSourceSpec,
        *,
        resolved_aoi: ResolvedAOI | None,
    ) -> Path:
        base_path = self.root_dir.joinpath(*spec.relative_path)
        if spec.locator_kind == "exact_path":
            if base_path.exists():
                return base_path
            if base_path.suffix.lower() == ".shp":
                gpkg_path = base_path.with_suffix(".gpkg")
                if gpkg_path.exists():
                    return gpkg_path
            raise FileNotFoundError(f"Raw source path does not exist for {spec.source_id}: {base_path}")
        if spec.locator_kind == "first_shp_in_dir":
            if not base_path.exists():
                raise FileNotFoundError(f"Raw source directory does not exist for {spec.source_id}: {base_path}")
            return _first_local_vector(base_path)
        if spec.locator_kind == "recursive_glob":
            matches = [
                path
                for pattern in _local_vector_glob_patterns(spec.glob_pattern or "**/*.shp")
                for path in sorted(base_path.glob(pattern))
            ]
            if not matches:
                raise FileNotFoundError(f"No vector source matched {spec.glob_pattern} under {base_path}")
            return self._select_recursive_glob_match(
                source_id=spec.source_id,
                matches=matches,
                resolved_aoi=resolved_aoi,
            )
        raise ValueError(f"Unsupported raw source locator_kind={spec.locator_kind}")

    @staticmethod
    def _select_recursive_glob_match(
        *,
        source_id: str,
        matches: list[Path],
        resolved_aoi: ResolvedAOI | None,
    ) -> Path:
        if len(matches) == 1:
            return matches[0]

        ranked = RawVectorSourceService._rank_recursive_glob_matches(matches, resolved_aoi=resolved_aoi)
        if ranked and ranked[0][0] > 0:
            top_score = ranked[0][0]
            top_matches = [path for score, path in ranked if score == top_score]
            if len(top_matches) == 1:
                return top_matches[0]

        candidate_list = ", ".join(str(path) for path in matches[:5])
        suffix = " ..." if len(matches) > 5 else ""
        raise ValueError(
            f"Ambiguous raw source match for {source_id}: "
            f"{candidate_list}{suffix}"
        )

    @staticmethod
    def _rank_recursive_glob_matches(
        matches: list[Path],
        *,
        resolved_aoi: ResolvedAOI | None,
    ) -> list[tuple[int, Path]]:
        if resolved_aoi is None:
            return [(0, path) for path in matches]

        exact_hints = [
            _normalize_path_hint(resolved_aoi.country_name),
            _normalize_path_hint(resolved_aoi.display_name),
            _normalize_path_hint(resolved_aoi.query),
        ]
        exact_hints = [hint for hint in exact_hints if hint]

        token_hints = set()
        token_hints.update(_tokenize_path_hint(resolved_aoi.country_name))
        token_hints.update(_tokenize_path_hint(resolved_aoi.display_name))
        token_hints.update(_tokenize_path_hint(resolved_aoi.query))
        if resolved_aoi.country_code:
            token_hints.add(str(resolved_aoi.country_code).strip().casefold())

        ranked: list[tuple[int, Path]] = []
        for path in matches:
            parts = [_normalize_path_hint(part) for part in path.parts]
            non_empty_parts = [part for part in parts if part]
            path_tokens = set()
            for part in non_empty_parts:
                path_tokens.update(part.split())

            score = 0
            for hint in exact_hints:
                if any(hint == part for part in non_empty_parts):
                    score += 20
            score += sum(1 for token in token_hints if token in path_tokens)
            ranked.append((score, path))

        ranked.sort(key=lambda item: (-item[0], str(item[1])))
        return ranked

    @staticmethod
    def _copy_cached_zip(*, cache_zip: Path, target_path: Path) -> Path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cache_zip, target_path)
        return target_path

    @staticmethod
    def _clip_cached_zip(
        *,
        cache_zip: Path,
        request_bbox: BBox,
        target_path: Path,
        resolved_aoi: ResolvedAOI | None = None,
    ) -> Path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if _has_boundary_clip(resolved_aoi):
            return clip_zip_to_boundary_path(
                cache_zip,
                target_path,
                boundary_path=Path(str(resolved_aoi.boundary_artifact_path)),
                request_bbox=request_bbox,
            )
        return clip_zip_to_request_bbox(cache_zip, target_path, request_bbox=request_bbox)

    @staticmethod
    def _bundle_feature_count(bundle_zip: Path) -> int:
        extract_dir = bundle_zip.parent / f"_inspect_{bundle_zip.stem}_{uuid.uuid4().hex[:8]}"
        shp_path = validate_zip_has_shapefile(bundle_zip, extract_dir)
        frame = gpd.read_file(shp_path)
        return len(frame.index)
