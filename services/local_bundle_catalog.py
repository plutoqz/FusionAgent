from __future__ import annotations

import uuid
import shutil
from pathlib import Path
from typing import Optional

import geopandas as gpd

from kg.source_catalog import CATALOG_BUNDLE_SPECS, CatalogBundleSpec
from services.aoi_resolution_service import ResolvedAOI
from services.input_acquisition_service import BBox, MaterializedInputBundle
from services.raw_vector_source_service import MaterializedRawVectorSource, RawVectorSourceService
from services.source_asset_service import SourceCoverageStatus, coverage_status_for_count
from utils.crs import normalize_target_crs
from utils.shp_zip import validate_zip_has_shapefile, zip_shapefile_bundle


BUILDING_SOURCE_FALLBACKS = {
    "catalog.earthquake.building": ["catalog.flood.building"],
}

PARTIAL_COVERAGE_ALLOWED_SOURCES = {
    "catalog.flood.road",
    "catalog.earthquake.road",
    "catalog.typhoon.road",
    "catalog.flood.water",
    "catalog.flood.waterways",
    "catalog.generic.poi",
}


class LocalBundleCatalogProvider:
    def __init__(self, root_dir: Path, *, raw_source_service: RawVectorSourceService) -> None:
        self.root_dir = Path(root_dir)
        self.raw_source_service = raw_source_service
        self.specs = {bundle_spec.source_id: bundle_spec for bundle_spec in CATALOG_BUNDLE_SPECS}

    def can_handle(self, source_id: str) -> bool:
        return source_id in self.specs

    def current_version(
        self,
        source_id: str,
        *,
        request_bbox: Optional[BBox] = None,
        resolved_aoi: ResolvedAOI | None = None,
    ) -> str:
        spec = self._spec_for(source_id)
        tokens = [
            self.raw_source_service.current_version(
                spec.osm_source_id,
                request_bbox=request_bbox,
                resolved_aoi=resolved_aoi,
            )
        ]
        if spec.ref_source_id is not None:
            try:
                tokens.append(
                    self.raw_source_service.current_version(
                        spec.ref_source_id,
                        request_bbox=request_bbox,
                        resolved_aoi=resolved_aoi,
                    )
                )
            except (FileNotFoundError, RuntimeError):
                if self._requires_complete_pair_coverage(source_id):
                    raise
                tokens.append(f"missing:{spec.ref_source_id}")
        return "|".join(tokens)

    def materialize(
        self,
        *,
        source_id: str,
        request_bbox: Optional[BBox],
        resolved_aoi: ResolvedAOI | None = None,
        target_dir: Path,
        target_crs: str,
    ) -> MaterializedInputBundle:
        return self._materialize_bundle(
            source_id=source_id,
            request_bbox=request_bbox,
            resolved_aoi=resolved_aoi,
            target_dir=target_dir,
            target_crs=target_crs,
            require_non_empty_pair=True,
        )

    def materialize_with_fallback(
        self,
        *,
        source_id: str,
        request_bbox: Optional[BBox],
        resolved_aoi: ResolvedAOI | None = None,
        target_dir: Path,
        target_crs: str,
    ) -> MaterializedInputBundle:
        attempted_sources = [source_id]
        combined_coverage: dict[str, SourceCoverageStatus] = {}
        requested = self._materialize_bundle(
            source_id=source_id,
            request_bbox=request_bbox,
            resolved_aoi=resolved_aoi,
            target_dir=target_dir,
            target_crs=target_crs,
            require_non_empty_pair=False,
        )
        combined_coverage.update(requested.component_coverage)
        if not self._has_empty_required_component(source_id, requested.component_coverage):
            return requested

        for fallback_source_id in BUILDING_SOURCE_FALLBACKS.get(source_id, []):
            attempted_sources.append(fallback_source_id)
            if target_dir.exists():
                shutil.rmtree(target_dir)
            fallback = self._materialize_bundle(
                source_id=fallback_source_id,
                request_bbox=request_bbox,
                resolved_aoi=resolved_aoi,
                target_dir=target_dir,
                target_crs=target_crs,
                require_non_empty_pair=False,
            )
            combined_coverage.update(fallback.component_coverage)
            if self._has_empty_required_component(fallback_source_id, fallback.component_coverage):
                continue
            return MaterializedInputBundle(
                osm_zip_path=fallback.osm_zip_path,
                ref_zip_path=fallback.ref_zip_path,
                bbox=fallback.bbox,
                target_crs=fallback.target_crs,
                source_id=fallback_source_id,
                fallback_from=source_id,
                attempted_sources=attempted_sources,
                component_coverage=combined_coverage,
            )

        raise ValueError(f"AOI-scoped bundle has empty source coverage for {source_id}")

    def _materialize_bundle(
        self,
        *,
        source_id: str,
        request_bbox: Optional[BBox],
        resolved_aoi: ResolvedAOI | None = None,
        target_dir: Path,
        target_crs: str,
        require_non_empty_pair: bool,
    ) -> MaterializedInputBundle:
        spec = self._spec_for(source_id)
        target_dir.mkdir(parents=True, exist_ok=True)

        osm = self.raw_source_service.resolve(
            source_id=spec.osm_source_id,
            request_bbox=request_bbox,
            target_path=target_dir / "osm.zip",
            target_crs=target_crs,
            resolved_aoi=resolved_aoi,
        )
        if spec.ref_source_id is not None:
            try:
                ref = self.raw_source_service.resolve(
                    source_id=spec.ref_source_id,
                    request_bbox=request_bbox,
                    target_path=target_dir / "ref.zip",
                    target_crs=target_crs,
                    resolved_aoi=resolved_aoi,
                )
            except (FileNotFoundError, RuntimeError):
                if not self._requires_complete_pair_coverage(source_id):
                    ref = self._create_empty_reference_bundle(
                        osm=osm,
                        output_zip=target_dir / "ref.zip",
                        source_id=spec.ref_source_id,
                        source_mode="missing_optional_ref",
                    )
                else:
                    raise
            osm_count = osm.feature_count or 0
            ref_count = ref.feature_count or 0
            if osm_count == 0 and ref_count == 0:
                raise ValueError(f"AOI-scoped bundle has empty source coverage for {source_id}")
            if require_non_empty_pair and self._requires_complete_pair_coverage(source_id):
                if osm_count == 0 or ref_count == 0:
                    raise ValueError(f"AOI-scoped bundle has empty source coverage for {source_id}")
        else:
            ref = self._create_empty_reference_bundle(osm=osm, output_zip=target_dir / "ref.zip")

        component_coverage = self._component_coverage(osm, ref, spec.component_source_ids)
        component_coverage.update(
            self._supplemental_component_coverage(
                source_id=source_id,
                request_bbox=request_bbox,
                resolved_aoi=resolved_aoi,
                target_dir=target_dir,
                target_crs=target_crs,
            )
        )
        return MaterializedInputBundle(
            osm_zip_path=osm.zip_path,
            ref_zip_path=ref.zip_path,
            bbox=osm.bbox or ref.bbox,
            target_crs=normalize_target_crs(target_crs),
            source_id=source_id,
            attempted_sources=[source_id],
            component_coverage=component_coverage,
        )

    def _spec_for(self, source_id: str) -> CatalogBundleSpec:
        return self.specs[source_id]

    @staticmethod
    def _component_coverage(
        osm: MaterializedRawVectorSource,
        ref: MaterializedRawVectorSource,
        component_source_ids: tuple[str, ...],
    ) -> dict[str, SourceCoverageStatus]:
        components = [(component_source_ids[0], osm)]
        if len(component_source_ids) == 2:
            components.append((component_source_ids[1], ref))
        return {
            source_id: SourceCoverageStatus(
                source_id=source_id,
                source_mode=component.source_mode,
                feature_count=component.feature_count,
                coverage_status=coverage_status_for_count(component.feature_count),
                path=component.zip_path,
            )
            for source_id, component in components
        }

    def _supplemental_component_coverage(
        self,
        *,
        source_id: str,
        request_bbox: Optional[BBox],
        resolved_aoi: ResolvedAOI | None,
        target_dir: Path,
        target_crs: str,
    ) -> dict[str, SourceCoverageStatus]:
        if source_id != "catalog.flood.water":
            return {}
        coverage: dict[str, SourceCoverageStatus] = {}
        for component_source_id in ("raw.osm.waterways", "raw.hydrorivers.water"):
            try:
                resolved = self.raw_source_service.resolve(
                    source_id=component_source_id,
                    request_bbox=request_bbox,
                    target_path=target_dir / f"{component_source_id.replace('.', '_')}.zip",
                    target_crs=target_crs,
                    resolved_aoi=resolved_aoi,
                )
            except (FileNotFoundError, RuntimeError, ValueError):
                continue
            coverage[component_source_id] = SourceCoverageStatus(
                source_id=component_source_id,
                source_mode=resolved.source_mode,
                feature_count=resolved.feature_count,
                coverage_status=coverage_status_for_count(resolved.feature_count),
                path=resolved.zip_path,
            )
        return coverage

    def _has_empty_required_component(
        self,
        source_id: str,
        component_coverage: dict[str, SourceCoverageStatus],
    ) -> bool:
        spec = self._spec_for(source_id)
        if spec.ref_source_id is None:
            return False
        if not self._requires_complete_pair_coverage(source_id):
            return False
        for component_source_id in spec.component_source_ids:
            status = component_coverage.get(component_source_id)
            if status is not None and status.feature_count == 0:
                return True
        return False

    @staticmethod
    def _requires_complete_pair_coverage(source_id: str) -> bool:
        return source_id not in PARTIAL_COVERAGE_ALLOWED_SOURCES

    @staticmethod
    def _create_empty_reference_bundle(
        *,
        osm: MaterializedRawVectorSource,
        output_zip: Path,
        source_id: str,
        source_mode: str = "generated_empty_ref",
    ) -> MaterializedRawVectorSource:
        extract_dir = output_zip.parent / f"_empty_ref_src_{uuid.uuid4().hex[:8]}"
        shp_path = validate_zip_has_shapefile(osm.zip_path, extract_dir)
        frame = gpd.read_file(shp_path)
        empty = frame.iloc[0:0].copy()

        out_dir = output_zip.parent / f"_empty_ref_dst_{uuid.uuid4().hex[:8]}"
        out_dir.mkdir(parents=True, exist_ok=True)
        ref_shp = out_dir / "ref.shp"
        empty.to_file(ref_shp)
        zip_shapefile_bundle(ref_shp, output_zip)

        return MaterializedRawVectorSource(
            zip_path=output_zip,
            bbox=osm.bbox,
            target_crs=osm.target_crs,
            source_id=source_id,
            source_mode=source_mode,
            cache_hit=False,
            version_token=osm.version_token,
            feature_count=0,
        )
