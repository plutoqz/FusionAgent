from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple

import geopandas as gpd
from shapely.geometry import box

from schemas.agent import RunArtifactMeta, RunCreateRequest, WorkflowPlan
from services.artifact_registry import ArtifactLookupRequest, ArtifactRecord, ArtifactRegistry
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
    text = value.strip()
    if not (text.startswith("bbox(") and text.endswith(")")):
        return None
    body = text[5:-1]
    parts = [part.strip() for part in body.split(",")]
    return _as_bbox(parts)


@dataclass(frozen=True)
class ReuseResult:
    mode: str
    source_record: ArtifactRecord
    artifact: RunArtifactMeta


class ArtifactReuseService:
    def __init__(self, registry: ArtifactRegistry, *, max_age_seconds: int = 7 * 24 * 60 * 60) -> None:
        self.registry = registry
        self.max_age_seconds = max_age_seconds

    def try_reuse(self, *, request: RunCreateRequest, plan: WorkflowPlan, output_dir: Path) -> Optional[ReuseResult]:
        request_bbox = _parse_bbox_text(request.trigger.spatial_extent)
        if request_bbox is None:
            return None

        candidate = self.registry.find_reusable(
            ArtifactLookupRequest(
                job_type=request.job_type.value,
                disaster_type=request.trigger.disaster_type,
                max_age_seconds=self.max_age_seconds,
                required_fields=[],
                bbox=request_bbox,
            )
        )
        if candidate is None:
            return None

        candidate_bbox = _as_bbox(candidate.bbox)
        if candidate_bbox is None:
            return None

        output_zip = output_dir / f"{request.job_type.value}_fusion_result.zip"
        if candidate_bbox == request_bbox:
            artifact = self._materialize_direct(candidate, output_zip=output_zip)
            return ReuseResult(mode="direct", source_record=candidate, artifact=artifact)

        artifact = self._materialize_clip(candidate, request_bbox=request_bbox, output_zip=output_zip)
        return ReuseResult(mode="clip", source_record=candidate, artifact=artifact)

    @staticmethod
    def _materialize_direct(record: ArtifactRecord, *, output_zip: Path) -> RunArtifactMeta:
        source_zip = Path(record.artifact_path)
        output_zip.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_zip, output_zip)
        return RunArtifactMeta(
            filename=output_zip.name,
            path=str(output_zip),
            size_bytes=output_zip.stat().st_size,
        )

    @staticmethod
    def _materialize_clip(record: ArtifactRecord, *, request_bbox: BBox, output_zip: Path) -> RunArtifactMeta:
        extract_dir = output_zip.parent / "_reuse_source_extract"
        clipped_dir = output_zip.parent / "_reuse_clip"
        source_shp = validate_zip_has_shapefile(Path(record.artifact_path), extract_dir)
        gdf = gpd.read_file(source_shp)
        clip_mask = box(*request_bbox)
        clipped = gdf.clip(clip_mask)
        clipped = clipped[~clipped.geometry.is_empty & clipped.geometry.notna()].copy()
        if clipped.empty:
            raise ValueError("Reusable artifact clip produced no features for the requested bbox.")

        clipped_dir.mkdir(parents=True, exist_ok=True)
        clipped_shp = clipped_dir / "artifact.shp"
        clipped.to_file(clipped_shp)
        zipped = zip_shapefile_bundle(clipped_shp, output_zip)
        return RunArtifactMeta(
            filename=zipped.name,
            path=str(zipped),
            size_bytes=zipped.stat().st_size,
        )
