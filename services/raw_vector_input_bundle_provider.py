from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

import geopandas as gpd

from services.aoi_resolution_service import ResolvedAOI
from services.input_acquisition_service import BBox, MaterializedInputBundle
from services.raw_vector_source_service import MaterializedRawVectorSource, RawVectorSourceService
from services.source_acquisition_policy import build_success_attempt
from services.source_asset_service import SourceCoverageStatus, coverage_status_for_count
from utils.crs import normalize_target_crs
from utils.shp_zip import validate_zip_has_shapefile, zip_shapefile_bundle


class RawVectorInputBundleProvider:
    def __init__(self, *, raw_source_service: RawVectorSourceService) -> None:
        self.raw_source_service = raw_source_service

    def can_handle(self, source_id: str) -> bool:
        return str(source_id).startswith("raw.") and self.raw_source_service.can_handle(source_id)

    def current_version(
        self,
        source_id: str,
        *,
        request_bbox: Optional[BBox] = None,
        resolved_aoi: ResolvedAOI | None = None,
    ) -> str:
        return self.raw_source_service.current_version(
            source_id,
            request_bbox=request_bbox,
            resolved_aoi=resolved_aoi,
        )

    def materialize(
        self,
        *,
        source_id: str,
        request_bbox: Optional[BBox],
        resolved_aoi: ResolvedAOI | None = None,
        target_dir: Path,
        target_crs: str,
    ) -> MaterializedInputBundle:
        normalized_crs = normalize_target_crs(target_crs)
        target_dir.mkdir(parents=True, exist_ok=True)
        raw = self.raw_source_service.resolve(
            source_id=source_id,
            request_bbox=request_bbox,
            target_path=target_dir / "osm.zip",
            target_crs=normalized_crs,
            resolved_aoi=resolved_aoi,
        )
        ref = _create_empty_companion_bundle(raw, target_dir / "ref.zip")
        coverage_status = coverage_status_for_count(raw.feature_count)

        return MaterializedInputBundle(
            osm_zip_path=raw.zip_path,
            ref_zip_path=ref.zip_path,
            bbox=raw.bbox,
            target_crs=normalized_crs,
            source_id=source_id,
            attempted_sources=[source_id],
            component_coverage={
                source_id: SourceCoverageStatus(
                    source_id=source_id,
                    source_mode=raw.source_mode,
                    feature_count=raw.feature_count,
                    coverage_status=coverage_status,
                    path=raw.zip_path,
                )
            },
            provider_attempts=[
                build_success_attempt(
                    source_id=source_id,
                    status="available" if coverage_status == "available" else "empty",
                    attempt_no=1,
                    coverage_status=coverage_status,
                    feature_count=raw.feature_count,
                    selected_for_fusion=coverage_status == "available",
                )
            ],
        )


def _create_empty_companion_bundle(raw: MaterializedRawVectorSource, output_zip: Path) -> MaterializedRawVectorSource:
    extract_dir = output_zip.parent / f"_empty_ref_src_{uuid.uuid4().hex[:8]}"
    shp_path = validate_zip_has_shapefile(raw.zip_path, extract_dir)
    frame = gpd.read_file(shp_path)
    empty = frame.iloc[0:0].copy()

    out_dir = output_zip.parent / f"_empty_ref_dst_{uuid.uuid4().hex[:8]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    ref_shp = out_dir / "ref.shp"
    empty.to_file(ref_shp)
    zip_shapefile_bundle(ref_shp, output_zip)

    return MaterializedRawVectorSource(
        zip_path=output_zip,
        bbox=raw.bbox,
        target_crs=raw.target_crs,
        source_id="generated.empty.reference",
        source_mode="generated_empty_ref",
        cache_hit=False,
        version_token=raw.version_token,
        feature_count=0,
        coverage_status="empty",
    )
