from __future__ import annotations

import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Protocol, Sequence, Tuple

import geopandas as gpd
from shapely.geometry import box

from schemas.agent import RunCreateRequest
from services.artifact_registry import ArtifactLookupRequest, ArtifactRecord, ArtifactRegistry
from utils.crs import normalize_target_crs
from utils.shp_zip import validate_zip_has_shapefile, zip_shapefile_bundle


BBox = Tuple[float, float, float, float]


def _as_bbox(value: Sequence[float] | None) -> Optional[BBox]:
    if value is None or len(value) != 4:
        return None
    try:
        minx, miny, maxx, maxy = (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
    except Exception:  # noqa: BLE001
        return None
    if maxx < minx or maxy < miny:
        return None
    return (minx, miny, maxx, maxy)


def _parse_bbox_text(value: str | None) -> Optional[BBox]:
    if not value:
        return None
    match = re.match(r"^bbox\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)\s*$", value)
    if not match:
        return None
    return _as_bbox([match.group(1), match.group(2), match.group(3), match.group(4)])


def _bundle_bbox_from_zip(zip_path: Path) -> Optional[BBox]:
    extract_dir = zip_path.parent / f"_inspect_{zip_path.stem}_{uuid.uuid4().hex[:8]}"
    shp_path = validate_zip_has_shapefile(zip_path, extract_dir)
    gdf = gpd.read_file(shp_path)
    if gdf.empty:
        return None
    minx, miny, maxx, maxy = [float(value) for value in gdf.total_bounds.tolist()]
    return (minx, miny, maxx, maxy)


class InputBundleProvider(Protocol):
    def can_handle(self, source_id: str) -> bool: ...

    def current_version(self, source_id: str) -> str: ...

    def materialize(
        self,
        *,
        source_id: str,
        request_bbox: Optional[BBox],
        target_dir: Path,
        target_crs: str,
    ) -> "MaterializedInputBundle": ...


@dataclass(frozen=True)
class MaterializedInputBundle:
    osm_zip_path: Path
    ref_zip_path: Path
    bbox: Optional[BBox]
    target_crs: str


@dataclass(frozen=True)
class ResolvedRunInputs:
    osm_zip_path: Path
    ref_zip_path: Path
    source_mode: str
    source_id: str
    cache_hit: bool
    version_token: str


class InputAcquisitionService:
    def __init__(self, *, registry: ArtifactRegistry, providers: list[InputBundleProvider], cache_dir: Path) -> None:
        self.registry = registry
        self.providers = providers
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def resolve_task_driven_inputs(
        self,
        *,
        request: RunCreateRequest,
        source_id: str,
        required_output_type: str,
        input_dir: Path,
    ) -> ResolvedRunInputs:
        provider = self._provider_for(source_id)
        version_token = provider.current_version(source_id)
        target_crs = normalize_target_crs(request.target_crs)
        request_bbox = _parse_bbox_text(request.trigger.spatial_extent)
        candidate = self.registry.find_reusable(
            ArtifactLookupRequest(
                job_type=request.job_type.value,
                required_output_type=required_output_type,
                required_target_crs=target_crs,
                bbox=request_bbox,
                required_meta={"artifact_role": "input_bundle", "source_id": source_id},
            )
        )

        if candidate is not None and candidate.meta.get("source_version") == version_token:
            bundle_dir = Path(candidate.artifact_path)
            if request_bbox is not None and candidate.bbox is not None and tuple(candidate.bbox) != request_bbox:
                clipped = self._clip_cached_bundle(bundle_dir=bundle_dir, request_bbox=request_bbox, input_dir=input_dir)
                return ResolvedRunInputs(
                    osm_zip_path=clipped.osm_zip_path,
                    ref_zip_path=clipped.ref_zip_path,
                    source_mode="clip_reused",
                    source_id=source_id,
                    cache_hit=True,
                    version_token=version_token,
                )
            copied = self._copy_cached_bundle(bundle_dir=bundle_dir, input_dir=input_dir)
            return ResolvedRunInputs(
                osm_zip_path=copied.osm_zip_path,
                ref_zip_path=copied.ref_zip_path,
                source_mode="cache_reused",
                source_id=source_id,
                cache_hit=True,
                version_token=version_token,
            )

        cache_bundle_dir = self.cache_dir / source_id.replace(".", "_") / version_token / uuid.uuid4().hex
        materialized = provider.materialize(
            source_id=source_id,
            request_bbox=request_bbox,
            target_dir=cache_bundle_dir,
            target_crs=target_crs,
        )
        bundle_bbox = materialized.bbox
        if bundle_bbox is None:
            bundle_bbox = _bundle_bbox_from_zip(materialized.osm_zip_path)
        self.registry.register(
            ArtifactRecord(
                artifact_id=f"input_bundle.{uuid.uuid4().hex}",
                artifact_path=str(cache_bundle_dir),
                job_type=request.job_type.value,
                disaster_type=request.trigger.disaster_type,
                created_at=datetime.now(timezone.utc).isoformat(),
                output_data_type=required_output_type,
                target_crs=target_crs,
                bbox=bundle_bbox,
                meta={
                    "artifact_role": "input_bundle",
                    "source_id": source_id,
                    "source_version": version_token,
                    "planning_mode": "task_driven",
                },
            )
        )
        copied = self._copy_cached_bundle(bundle_dir=cache_bundle_dir, input_dir=input_dir)
        return ResolvedRunInputs(
            osm_zip_path=copied.osm_zip_path,
            ref_zip_path=copied.ref_zip_path,
            source_mode="downloaded",
            source_id=source_id,
            cache_hit=False,
            version_token=version_token,
        )

    def _provider_for(self, source_id: str) -> InputBundleProvider:
        for provider in self.providers:
            if provider.can_handle(source_id):
                return provider
        raise ValueError(f"No input bundle provider registered for source_id={source_id}")

    @staticmethod
    def _copy_cached_bundle(*, bundle_dir: Path, input_dir: Path) -> MaterializedInputBundle:
        input_dir.mkdir(parents=True, exist_ok=True)
        osm_out = input_dir / "osm.zip"
        ref_out = input_dir / "ref.zip"
        shutil.copyfile(bundle_dir / "osm.zip", osm_out)
        shutil.copyfile(bundle_dir / "ref.zip", ref_out)
        return MaterializedInputBundle(
            osm_zip_path=osm_out,
            ref_zip_path=ref_out,
            bbox=_bundle_bbox_from_zip(osm_out),
            target_crs="",
        )

    def _clip_cached_bundle(self, *, bundle_dir: Path, request_bbox: BBox, input_dir: Path) -> MaterializedInputBundle:
        input_dir.mkdir(parents=True, exist_ok=True)
        osm_zip = self._clip_single_zip(bundle_dir / "osm.zip", input_dir / "osm.zip", request_bbox=request_bbox)
        ref_zip = self._clip_single_zip(bundle_dir / "ref.zip", input_dir / "ref.zip", request_bbox=request_bbox)
        return MaterializedInputBundle(
            osm_zip_path=osm_zip,
            ref_zip_path=ref_zip,
            bbox=request_bbox,
            target_crs="",
        )

    @staticmethod
    def _clip_single_zip(source_zip: Path, output_zip: Path, *, request_bbox: BBox) -> Path:
        extract_dir = output_zip.parent / f"_clip_src_{source_zip.stem}_{uuid.uuid4().hex[:8]}"
        shp_path = validate_zip_has_shapefile(source_zip, extract_dir)
        gdf = gpd.read_file(shp_path)
        clipped = gdf.clip(box(*request_bbox))
        clipped = clipped[~clipped.geometry.is_empty & clipped.geometry.notna()].copy()
        if clipped.empty:
            clipped = gdf.iloc[0:0].copy()
        out_dir = output_zip.parent / f"_clip_dst_{source_zip.stem}_{uuid.uuid4().hex[:8]}"
        out_dir.mkdir(parents=True, exist_ok=True)
        clipped_shp = out_dir / shp_path.name
        clipped.to_file(clipped_shp)
        return zip_shapefile_bundle(clipped_shp, output_zip)
