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
from services.source_acquisition_policy import (
    EXTERNAL_UNCONTROLLABLE_FAULTS,
    build_source_attempt,
    build_success_attempt,
    requires_complete_pair_coverage,
    required_full_closure_source_ids,
    source_component_candidates,
    source_fallback_candidates,
)
from services.raster_height_source_service import RasterHeightSourceService
from services.runtime_source_aliases import BUILDING_HEIGHT_RASTER_PRIORITY_ORDER
from services.source_asset_service import SourceCoverageStatus, coverage_status_for_count
from utils.crs import normalize_target_crs
from utils.shp_zip import validate_zip_has_shapefile, zip_shapefile_bundle


BUILDING_SOURCE_FALLBACKS = {
    "catalog.earthquake.building": source_fallback_candidates("catalog.earthquake.building"),
}

PARTIAL_COVERAGE_ALLOWED_SOURCES = {
    "catalog.flood.road",
    "catalog.earthquake.road",
    "catalog.typhoon.road",
    "catalog.flood.water",
    "catalog.generic.poi",
}


class LocalBundleCatalogProvider:
    def __init__(
        self,
        root_dir: Path,
        *,
        raw_source_service: RawVectorSourceService,
        raster_height_source_service: RasterHeightSourceService | None = None,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.raw_source_service = raw_source_service
        self.raster_height_source_service = raster_height_source_service
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
        policy_candidates = self._materialization_candidates(
            source_id=source_id,
            candidates=source_component_candidates(source_id, ()),
            request_bbox=request_bbox,
            resolved_aoi=resolved_aoi,
        )
        if policy_candidates:
            tokens = []
            for component_source_id in policy_candidates:
                try:
                    tokens.append(
                        self.raw_source_service.current_version(
                            component_source_id,
                            request_bbox=request_bbox,
                            resolved_aoi=resolved_aoi,
                        )
                    )
                except (FileNotFoundError, RuntimeError, PermissionError, KeyError, ValueError):
                    tokens.append(f"missing:{component_source_id}")
            if self._is_building_catalog(source_id) and self.raster_height_source_service is not None:
                tokens.extend(
                    self.raster_height_source_service.current_version_tokens(resolved_aoi=resolved_aoi)
                )
            return "|".join(tokens)

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
        combined_provider_attempts: list[dict[str, object]] = []
        requested: MaterializedInputBundle | None = None
        try:
            requested = self._materialize_bundle(
                source_id=source_id,
                request_bbox=request_bbox,
                resolved_aoi=resolved_aoi,
                target_dir=target_dir,
                target_crs=target_crs,
                require_non_empty_pair=False,
            )
        except ValueError as exc:
            if "empty source coverage" not in str(exc):
                raise
        if requested is not None:
            combined_coverage.update(requested.component_coverage)
            combined_provider_attempts.extend(requested.provider_attempts)
            if not self._has_empty_required_component(source_id, requested.component_coverage):
                return requested

        for fallback_source_id in source_fallback_candidates(source_id):
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
            combined_provider_attempts.extend(fallback.provider_attempts)
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
                provider_attempts=self._renumber_provider_attempts(combined_provider_attempts),
            )

        if requested is not None and any((status.feature_count or 0) > 0 for status in combined_coverage.values()):
            return MaterializedInputBundle(
                osm_zip_path=requested.osm_zip_path,
                ref_zip_path=requested.ref_zip_path,
                bbox=requested.bbox,
                target_crs=requested.target_crs,
                source_id=requested.source_id,
                fallback_from=requested.fallback_from,
                attempted_sources=attempted_sources,
                component_coverage=combined_coverage,
                provider_attempts=self._renumber_provider_attempts(combined_provider_attempts),
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

        policy_candidates = self._materialization_candidates(
            source_id=source_id,
            candidates=source_component_candidates(source_id, ()),
            request_bbox=request_bbox,
            resolved_aoi=resolved_aoi,
        )
        if policy_candidates:
            return self._materialize_policy_candidate_bundle(
                spec=spec,
                source_id=source_id,
                candidates=policy_candidates,
                request_bbox=request_bbox,
                resolved_aoi=resolved_aoi,
                target_dir=target_dir,
                target_crs=target_crs,
            )

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

    def _materialize_policy_candidate_bundle(
        self,
        *,
        spec: CatalogBundleSpec,
        source_id: str,
        candidates: list[str],
        request_bbox: Optional[BBox],
        resolved_aoi: ResolvedAOI | None,
        target_dir: Path,
        target_crs: str,
    ) -> MaterializedInputBundle:
        resolved_components: dict[str, MaterializedRawVectorSource] = {}
        component_coverage: dict[str, SourceCoverageStatus] = {}
        provider_attempts: list[dict[str, object]] = []

        target_paths = self._candidate_target_paths(
            spec=spec,
            candidates=candidates,
            target_dir=target_dir,
        )
        for component_source_id in candidates:
            target_path = target_paths.get(component_source_id, target_dir / f"{component_source_id.replace('.', '_')}.zip")
            try:
                resolved = self.raw_source_service.resolve(
                    source_id=component_source_id,
                    request_bbox=request_bbox,
                    target_path=target_path,
                    target_crs=target_crs,
                    resolved_aoi=resolved_aoi,
                )
            except (FileNotFoundError, RuntimeError, PermissionError, KeyError, ValueError) as exc:
                source_mode, fault_class = self._source_attempt_fault(component_source_id, exc)
                coverage_status = "awaiting_external_config" if fault_class == "CONFIG_MISSING" else "missing"
                component_coverage[component_source_id] = SourceCoverageStatus(
                    source_id=component_source_id,
                    source_mode=source_mode,
                    feature_count=0,
                    coverage_status=coverage_status,
                    path=None,
                    error=str(exc),
                    fault_class=fault_class,
                    external_uncontrollable=fault_class in EXTERNAL_UNCONTROLLABLE_FAULTS,
                )
                provider_attempts.append(
                    build_source_attempt(
                        source_id=component_source_id,
                        status=coverage_status if fault_class == "CONFIG_MISSING" else "failed",
                        fault_class=fault_class,
                        fault_message=str(exc),
                        attempt_no=len(provider_attempts) + 1,
                        recoverable=False if fault_class == "CONFIG_MISSING" else None,
                    )
                )
                continue

            resolved_components[component_source_id] = resolved
            coverage_status = coverage_status_for_count(resolved.feature_count)
            if coverage_status == "empty" and component_source_id == "raw.microsoft.building":
                coverage_status = "coverage_empty"
            component_coverage[component_source_id] = SourceCoverageStatus(
                source_id=component_source_id,
                source_mode=resolved.source_mode,
                feature_count=resolved.feature_count,
                coverage_status=coverage_status,
                path=resolved.zip_path,
            )
            provider_attempts.append(
                build_success_attempt(
                    source_id=component_source_id,
                    status="available" if coverage_status == "available" else "empty",
                    attempt_no=len(provider_attempts) + 1,
                    coverage_status=coverage_status,
                    feature_count=resolved.feature_count,
                    selected_for_fusion=coverage_status == "available",
                )
            )

        if self._is_building_catalog(source_id) and self.raster_height_source_service is not None:
            raster_coverage, raster_attempts = self.raster_height_source_service.materialize_preferred(
                target_dir=target_dir / "height_rasters",
                request_bbox=request_bbox,
                resolved_aoi=resolved_aoi,
                source_ids=BUILDING_HEIGHT_RASTER_PRIORITY_ORDER,
                starting_attempt_no=len(provider_attempts) + 1,
            )
            component_coverage.update(raster_coverage)
            provider_attempts.extend(raster_attempts)

        osm = resolved_components.get(spec.osm_source_id)
        ref_source_id = self._candidate_ref_source_id(spec=spec, candidates=candidates)
        ref = resolved_components.get(ref_source_id) if ref_source_id is not None else None
        has_any_candidate_coverage = any(_coverage_feature_count(status) > 0 for status in component_coverage.values())
        if not has_any_candidate_coverage:
            raise ValueError(f"AOI-scoped bundle has empty source coverage for {source_id}")

        if ref is None:
            first_available_ref = next(
                (
                    component
                    for component in resolved_components.values()
                    if component.source_id != spec.osm_source_id and (component.feature_count or 0) > 0
                ),
                None,
            )
            if first_available_ref is not None:
                ref = self._ensure_component_zip_path(
                    component=first_available_ref,
                    output_zip=target_dir / "ref.zip",
                )
                ref_source_id = first_available_ref.source_id
                component_coverage[ref_source_id] = SourceCoverageStatus(
                    source_id=ref_source_id,
                    source_mode=ref.source_mode,
                    feature_count=ref.feature_count,
                    coverage_status=coverage_status_for_count(ref.feature_count),
                    path=ref.zip_path,
                )

        if osm is None:
            if ref is None:
                raise ValueError(f"AOI-scoped bundle has empty source coverage for {source_id}")
            osm = self._create_empty_reference_bundle(
                osm=ref,
                output_zip=target_dir / "osm.zip",
                source_id=spec.osm_source_id,
                source_mode="missing_optional_osm",
            )
            component_coverage[spec.osm_source_id] = SourceCoverageStatus(
                source_id=spec.osm_source_id,
                source_mode=osm.source_mode,
                feature_count=0,
                coverage_status="empty",
                path=osm.zip_path,
            )
        if ref is None:
            ref = self._create_empty_reference_bundle(
                osm=osm,
                output_zip=target_dir / "ref.zip",
                source_id=ref_source_id or spec.ref_source_id or "ref",
                source_mode="missing_optional_ref",
            )
            if ref_source_id is not None and ref_source_id not in component_coverage:
                component_coverage[ref_source_id] = SourceCoverageStatus(
                    source_id=ref_source_id,
                    source_mode=ref.source_mode,
                    feature_count=0,
                    coverage_status="empty",
                    path=ref.zip_path,
                )

        return MaterializedInputBundle(
            osm_zip_path=osm.zip_path,
            ref_zip_path=ref.zip_path,
            bbox=osm.bbox or ref.bbox,
            target_crs=normalize_target_crs(target_crs),
            source_id=source_id,
            attempted_sources=[source_id],
            component_coverage=component_coverage,
            provider_attempts=provider_attempts,
        )

    @staticmethod
    def _is_building_catalog(source_id: str) -> bool:
        return source_id in {"catalog.flood.building", "catalog.earthquake.building"}

    def _materialization_candidates(
        self,
        *,
        source_id: str,
        candidates: list[str],
        request_bbox: Optional[BBox],
        resolved_aoi: ResolvedAOI | None,
    ) -> list[str]:
        materialization_candidates = list(candidates)
        if source_id not in {"catalog.flood.road", "catalog.earthquake.road", "catalog.typhoon.road"}:
            return materialization_candidates
        if "raw.overture.road" in materialization_candidates:
            return materialization_candidates
        resolve_local_source_path = getattr(self.raw_source_service, "resolve_local_source_path", None)
        if not callable(resolve_local_source_path):
            return materialization_candidates
        try:
            resolve_local_source_path("raw.overture.road", resolved_aoi=resolved_aoi)
        except (FileNotFoundError, RuntimeError, PermissionError, KeyError, ValueError):
            return materialization_candidates
        return [*materialization_candidates, "raw.overture.road"]

    @staticmethod
    def _candidate_target_paths(
        *,
        spec: CatalogBundleSpec,
        candidates: list[str],
        target_dir: Path,
    ) -> dict[str, Path]:
        target_paths: dict[str, Path] = {}
        if spec.osm_source_id in candidates:
            target_paths[spec.osm_source_id] = target_dir / "osm.zip"
        ref_source_id = LocalBundleCatalogProvider._candidate_ref_source_id(spec=spec, candidates=candidates)
        if ref_source_id is not None:
            target_paths[ref_source_id] = target_dir / "ref.zip"
        return target_paths

    @staticmethod
    def _candidate_ref_source_id(*, spec: CatalogBundleSpec, candidates: list[str]) -> str | None:
        if spec.ref_source_id is not None and spec.ref_source_id in candidates:
            return spec.ref_source_id
        return next((candidate for candidate in candidates if candidate != spec.osm_source_id), None)

    @staticmethod
    def _ensure_component_zip_path(
        *,
        component: MaterializedRawVectorSource,
        output_zip: Path,
    ) -> MaterializedRawVectorSource:
        if component.zip_path == output_zip:
            return component
        output_zip.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(component.zip_path, output_zip)
        return MaterializedRawVectorSource(
            zip_path=output_zip,
            bbox=component.bbox,
            target_crs=component.target_crs,
            source_id=component.source_id,
            source_mode=component.source_mode,
            cache_hit=component.cache_hit,
            version_token=component.version_token,
            feature_count=component.feature_count,
            coverage_status=component.coverage_status,
        )

    @staticmethod
    def _source_attempt_fault(source_id: str, exc: Exception) -> tuple[str, str]:
        text = str(exc).casefold()
        if source_id in {"raw.google.building", "raw.google.open_buildings.vector"} and (
            "not configured" in text
            or "url index is not configured" in text
            or "cache key" in text
        ):
            return "awaiting_external_config", "CONFIG_MISSING"
        if source_id == "raw.google.poi" and "google_places_api_key" in text:
            return "awaiting_external_config", "CONFIG_MISSING"
        if isinstance(exc, PermissionError):
            return "unauthorized", "UNAUTHORIZED"
        if isinstance(exc, (FileNotFoundError, KeyError)):
            return "missing_optional_ref", "SOURCE_MISSING"
        return "provider_failed", "PROVIDER_UNAVAILABLE"

    @staticmethod
    def _renumber_provider_attempts(attempts: list[dict[str, object]]) -> list[dict[str, object]]:
        renumbered: list[dict[str, object]] = []
        for index, attempt in enumerate(attempts, start=1):
            payload = dict(attempt)
            payload["attempt_no"] = index
            renumbered.append(payload)
        return renumbered

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
            if status is not None and _coverage_feature_count(status) == 0:
                return True
        return False

    @staticmethod
    def _requires_complete_pair_coverage(source_id: str) -> bool:
        return requires_complete_pair_coverage(source_id)

    @staticmethod
    def _required_full_closure_source_ids(source_id: str) -> list[str]:
        return required_full_closure_source_ids(source_id)

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


def _coverage_feature_count(status: object) -> int:
    if isinstance(status, dict):
        value = status.get("feature_count")
    else:
        value = getattr(status, "feature_count", None)
    if isinstance(value, bool):
        return 0
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
