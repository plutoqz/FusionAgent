from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import geopandas as gpd
from shapely.geometry import box

from schemas.agent import RunArtifactMeta, RunCreateRequest, WorkflowPlan
from services.artifact_reuse_policy import get_artifact_reuse_max_age_seconds
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
    def __init__(self, registry: ArtifactRegistry) -> None:
        self.registry = registry

    def try_reuse(self, *, request: RunCreateRequest, plan: WorkflowPlan, output_dir: Path) -> Optional[ReuseResult]:
        request_bbox = _parse_bbox_text(request.trigger.spatial_extent)
        if request_bbox is None:
            return None
        required_output_type = self._required_output_type(plan)
        required_fields = self._required_fields(plan, required_output_type=required_output_type)
        required_target_crs = normalize_target_crs(request.target_crs)

        candidate = self.registry.find_reusable(
            ArtifactLookupRequest(
                job_type=request.job_type.value,
                disaster_type=request.trigger.disaster_type,
                max_age_seconds=get_artifact_reuse_max_age_seconds(request.job_type),
                required_fields=required_fields,
                required_output_type=required_output_type,
                required_target_crs=required_target_crs,
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

        artifact = self._materialize_clip(
            candidate,
            request_bbox=request_bbox,
            output_zip=output_zip,
            required_fields=required_fields,
            required_target_crs=required_target_crs,
        )
        return ReuseResult(mode="clip", source_record=candidate, artifact=artifact)

    @staticmethod
    def _required_output_type(plan: WorkflowPlan) -> Optional[str]:
        ordered_tasks = sorted(plan.tasks, key=lambda item: item.step)
        for task in reversed(ordered_tasks):
            output_type = str(task.output.data_type_id or "").strip()
            if output_type:
                return output_type
        return None

    @staticmethod
    def _required_fields(plan: WorkflowPlan, *, required_output_type: Optional[str]) -> List[str]:
        retrieval = plan.context.get("retrieval", {})
        raw_policies = retrieval.get("output_schema_policies", {}) if isinstance(retrieval, dict) else {}
        if not isinstance(raw_policies, dict) or not required_output_type:
            return []
        raw_policy = raw_policies.get(required_output_type)
        if not isinstance(raw_policy, dict):
            return []
        required_fields = raw_policy.get("required_fields", [])
        if not isinstance(required_fields, list):
            return []
        normalized: List[str] = []
        for field in required_fields:
            token = str(field).strip()
            if not token or token.lower() == "geometry":
                continue
            if token not in normalized:
                normalized.append(token)
        return normalized

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
    def _materialize_clip(
        record: ArtifactRecord,
        *,
        request_bbox: BBox,
        output_zip: Path,
        required_fields: List[str],
        required_target_crs: str,
    ) -> RunArtifactMeta:
        extract_dir = output_zip.parent / "_reuse_source_extract"
        clipped_dir = output_zip.parent / "_reuse_clip"
        source_shp = validate_zip_has_shapefile(Path(record.artifact_path), extract_dir)
        gdf = gpd.read_file(source_shp)
        clip_mask = box(*request_bbox)
        clipped = gdf.clip(clip_mask)
        clipped = clipped[~clipped.geometry.is_empty & clipped.geometry.notna()].copy()
        if clipped.empty:
            raise ValueError("Reusable artifact clip produced no features for the requested bbox.")
        ArtifactReuseService._validate_clipped_output(
            clipped,
            required_fields=required_fields,
            required_target_crs=required_target_crs,
            request_bbox=request_bbox,
        )

        clipped_dir.mkdir(parents=True, exist_ok=True)
        clipped_shp = clipped_dir / "artifact.shp"
        clipped.to_file(clipped_shp)
        zipped = zip_shapefile_bundle(clipped_shp, output_zip)
        return RunArtifactMeta(
            filename=zipped.name,
            path=str(zipped),
            size_bytes=zipped.stat().st_size,
        )

    @staticmethod
    def _validate_clipped_output(
        gdf: gpd.GeoDataFrame,
        *,
        required_fields: List[str],
        required_target_crs: str,
        request_bbox: BBox,
    ) -> None:
        actual_target_crs = ArtifactReuseService._normalize_frame_crs(gdf)
        if actual_target_crs != required_target_crs:
            raise ValueError(
                f"Reusable artifact clip CRS mismatch: expected {required_target_crs}, got {actual_target_crs or 'unknown'}."
            )

        missing_fields = [field for field in required_fields if field not in gdf.columns]
        if missing_fields:
            raise ValueError(
                "Reusable artifact clip is missing required fields: " + ", ".join(sorted(missing_fields))
            )

        minx, miny, maxx, maxy = [float(value) for value in gdf.total_bounds.tolist()]
        req_minx, req_miny, req_maxx, req_maxy = request_bbox
        tolerance = 1e-9
        if (
            minx < req_minx - tolerance
            or miny < req_miny - tolerance
            or maxx > req_maxx + tolerance
            or maxy > req_maxy + tolerance
        ):
            raise ValueError(
                "Reusable artifact clip escaped the requested bbox bounds and was rejected as unsafe."
            )

    @staticmethod
    def _normalize_frame_crs(gdf: gpd.GeoDataFrame) -> Optional[str]:
        crs = getattr(gdf, "crs", None)
        if crs is None:
            return None
        try:
            if hasattr(crs, "to_epsg"):
                epsg = crs.to_epsg()
                if epsg:
                    return normalize_target_crs(f"EPSG:{epsg}")
        except Exception:  # noqa: BLE001
            pass
        try:
            return normalize_target_crs(str(crs))
        except Exception:  # noqa: BLE001
            return None
