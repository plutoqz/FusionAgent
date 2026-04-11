from __future__ import annotations

import hashlib
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import geopandas as gpd

from kg.source_catalog import RAW_VECTOR_SOURCE_SPECS, RawVectorSourceSpec, get_raw_vector_source_spec
from services.artifact_registry import ArtifactLookupRequest, ArtifactRecord, ArtifactRegistry
from utils.crs import normalize_target_crs
from utils.shp_zip import collect_bundle_files, zip_shapefile_bundle
from utils.vector_clip import BBox, REQUEST_BBOX_CRS, clip_frame_to_request_bbox, clip_zip_to_request_bbox, frame_bbox_in_crs


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _first_shp(directory: Path) -> Path:
    matches = sorted(directory.glob("*.shp"))
    if not matches:
        raise FileNotFoundError(f"No shapefile found in {directory}")
    return matches[0]


def _bundle_version_token(shp_path: Path) -> str:
    files = collect_bundle_files(shp_path)
    if not files:
        raise FileNotFoundError(f"No shapefile bundle files found near {shp_path}")
    payload = "|".join(f"{file.name}:{int(file.stat().st_mtime)}:{file.stat().st_size}" for file in files)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MaterializedRawVectorSource:
    zip_path: Path
    bbox: Optional[BBox]
    target_crs: str
    source_id: str
    source_mode: str
    cache_hit: bool
    version_token: str


class RawVectorSourceService:
    def __init__(self, *, root_dir: Path, registry: ArtifactRegistry, cache_dir: Path) -> None:
        self.root_dir = Path(root_dir)
        self.registry = registry
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.specs = {spec.source_id: spec for spec in RAW_VECTOR_SOURCE_SPECS}

    def can_handle(self, source_id: str) -> bool:
        return source_id in self.specs

    def current_version(self, source_id: str) -> str:
        shp_path = self._resolve_source_path(get_raw_vector_source_spec(source_id))
        return _bundle_version_token(shp_path)

    def resolve(
        self,
        *,
        source_id: str,
        request_bbox: Optional[BBox],
        target_path: Path,
        target_crs: str,
    ) -> MaterializedRawVectorSource:
        normalized_target_crs = normalize_target_crs(target_crs)
        version_token = self.current_version(source_id)
        candidate = self.registry.find_reusable(
            ArtifactLookupRequest(
                required_output_type="dt.raw.vector",
                required_target_crs=normalized_target_crs,
                bbox=request_bbox,
                required_meta={"artifact_role": "raw_vector", "source_id": source_id},
            )
        )
        if candidate is not None and candidate.meta.get("source_version") == version_token:
            cache_zip = Path(candidate.artifact_path)
            if request_bbox is not None and candidate.bbox is not None and tuple(candidate.bbox) != request_bbox:
                clipped = self._clip_cached_zip(cache_zip=cache_zip, request_bbox=request_bbox, target_path=target_path)
                return MaterializedRawVectorSource(
                    zip_path=clipped,
                    bbox=request_bbox,
                    target_crs=normalized_target_crs,
                    source_id=source_id,
                    source_mode="clip_reused",
                    cache_hit=True,
                    version_token=version_token,
                )
            copied = self._copy_cached_zip(cache_zip=cache_zip, target_path=target_path)
            return MaterializedRawVectorSource(
                zip_path=copied,
                bbox=tuple(candidate.bbox) if candidate.bbox is not None else None,
                target_crs=normalized_target_crs,
                source_id=source_id,
                source_mode="cache_reused",
                cache_hit=True,
                version_token=version_token,
            )

        cache_zip = self.cache_dir / source_id.replace(".", "_") / version_token / uuid.uuid4().hex / "source.zip"
        materialized = self._materialize_from_source(
            source_id=source_id,
            request_bbox=request_bbox,
            target_path=cache_zip,
            target_crs=normalized_target_crs,
        )
        self.registry.register(
            ArtifactRecord(
                artifact_id=f"raw_vector.{uuid.uuid4().hex}",
                artifact_path=str(cache_zip),
                job_type="raw_vector",
                created_at=_utc_now(),
                output_data_type="dt.raw.vector",
                target_crs=normalized_target_crs,
                bbox=materialized.bbox,
                meta={
                    "artifact_role": "raw_vector",
                    "source_id": source_id,
                    "source_version": version_token,
                },
            )
        )
        copied = self._copy_cached_zip(cache_zip=cache_zip, target_path=target_path)
        return MaterializedRawVectorSource(
            zip_path=copied,
            bbox=materialized.bbox,
            target_crs=normalized_target_crs,
            source_id=source_id,
            source_mode="downloaded",
            cache_hit=False,
            version_token=version_token,
        )

    def _materialize_from_source(
        self,
        *,
        source_id: str,
        request_bbox: Optional[BBox],
        target_path: Path,
        target_crs: str,
    ) -> MaterializedRawVectorSource:
        spec = get_raw_vector_source_spec(source_id)
        shp_path = self._resolve_source_path(spec)
        gdf = gpd.read_file(shp_path)
        clipped = clip_frame_to_request_bbox(gdf, request_bbox, request_crs=REQUEST_BBOX_CRS)
        request_space_bbox = frame_bbox_in_crs(clipped, bbox_crs=REQUEST_BBOX_CRS)

        projected = clipped
        if not projected.empty:
            projected = projected.to_crs(target_crs)
        else:
            projected = projected.set_crs(clipped.crs or REQUEST_BBOX_CRS).to_crs(target_crs)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        out_dir = target_path.parent / f"bundle_{uuid.uuid4().hex[:8]}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_shp = out_dir / shp_path.name
        projected.to_file(out_shp)
        zip_shapefile_bundle(out_shp, target_path)

        return MaterializedRawVectorSource(
            zip_path=target_path,
            bbox=request_space_bbox,
            target_crs=target_crs,
            source_id=source_id,
            source_mode="downloaded",
            cache_hit=False,
            version_token=self.current_version(source_id),
        )

    def _resolve_source_path(self, spec: RawVectorSourceSpec) -> Path:
        base_path = self.root_dir.joinpath(*spec.relative_path)
        if spec.locator_kind == "exact_path":
            if not base_path.exists():
                raise FileNotFoundError(f"Raw source path does not exist for {spec.source_id}: {base_path}")
            return base_path
        if spec.locator_kind == "first_shp_in_dir":
            if not base_path.exists():
                raise FileNotFoundError(f"Raw source directory does not exist for {spec.source_id}: {base_path}")
            return _first_shp(base_path)
        if spec.locator_kind == "recursive_glob":
            matches = sorted(base_path.glob(spec.glob_pattern or "**/*.shp"))
            if not matches:
                raise FileNotFoundError(f"No shapefile matched {spec.glob_pattern} under {base_path}")
            return matches[0]
        raise ValueError(f"Unsupported raw source locator_kind={spec.locator_kind}")

    @staticmethod
    def _copy_cached_zip(*, cache_zip: Path, target_path: Path) -> Path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cache_zip, target_path)
        return target_path

    @staticmethod
    def _clip_cached_zip(*, cache_zip: Path, request_bbox: BBox, target_path: Path) -> Path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        return clip_zip_to_request_bbox(cache_zip, target_path, request_bbox=request_bbox)
