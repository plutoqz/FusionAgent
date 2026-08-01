from __future__ import annotations

import shutil
import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

import geopandas as gpd

from kg.knowledge_release import KnowledgeReleaseError
from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry
from kg.source_catalog import CATALOG_BUNDLE_SPECS, CatalogBundleSpec
from schemas.data_requirement import BundleSlot, CompletenessPolicy, DataRequirementPlan, SourceRoleRequirement
from schemas.failure_taxonomy import classify_failure_category
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


@dataclass(frozen=True)
class RoleAwareSourceCoverageStatus(SourceCoverageStatus):
    role_id: str = ""
    role_ids: tuple[str, ...] = ()
    role_contract: dict[str, object] | None = None
    role_contracts: tuple[dict[str, object], ...] = ()
    selected_role_ids: tuple[str, ...] = ()


class BundleMaterializationError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        component_coverage: dict[str, object] | None = None,
        provider_attempts: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(message)
        self.component_coverage = dict(component_coverage or {})
        self.provider_attempts = [dict(attempt) for attempt in (provider_attempts or [])]


class LocalBundleCatalogProvider:
    def __init__(
        self,
        root_dir: Path,
        *,
        raw_source_service: RawVectorSourceService,
        raster_height_source_service: RasterHeightSourceService | None = None,
        policy_registry: KnowledgePolicyRegistry | None = None,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.raw_source_service = raw_source_service
        self.raster_height_source_service = raster_height_source_service
        self.policy_registry = policy_registry or default_policy_registry()
        self.specs = {bundle_spec.source_id: bundle_spec for bundle_spec in CATALOG_BUNDLE_SPECS}

    def can_handle(self, source_id: str) -> bool:
        return source_id in self.specs

    def current_version(
        self,
        source_id: str,
        *,
        request_bbox: Optional[BBox] = None,
        resolved_aoi: ResolvedAOI | None = None,
        data_requirements: DataRequirementPlan | None = None,
    ) -> str:
        self._spec_for(source_id)
        policy_candidates = self._candidate_source_ids(
            source_id=source_id,
            data_requirements=data_requirements,
        )
        tokens: list[str] = []
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
        height_source_ids = self._height_source_ids(data_requirements)
        if self._is_building_catalog(source_id) and self.raster_height_source_service is not None and height_source_ids:
            tokens.extend(
                self.raster_height_source_service.current_version_tokens(
                    resolved_aoi=resolved_aoi,
                    source_ids=height_source_ids,
                )
            )
        return "|".join(tokens)

    def materialize(
        self,
        *,
        source_id: str,
        request_bbox: Optional[BBox],
        resolved_aoi: ResolvedAOI | None = None,
        target_dir: Path,
        target_crs: str,
        data_requirements: DataRequirementPlan | None = None,
    ) -> MaterializedInputBundle:
        return self._materialize_bundle(
            source_id=source_id,
            request_bbox=request_bbox,
            resolved_aoi=resolved_aoi,
            target_dir=target_dir,
            target_crs=target_crs,
            data_requirements=data_requirements,
        )

    def materialize_with_fallback(
        self,
        *,
        source_id: str,
        request_bbox: Optional[BBox],
        resolved_aoi: ResolvedAOI | None = None,
        target_dir: Path,
        target_crs: str,
        data_requirements: DataRequirementPlan | None = None,
    ) -> MaterializedInputBundle:
        attempted_sources = [source_id]
        combined_coverage: dict[str, object] = {}
        combined_provider_attempts: list[dict[str, object]] = []
        try:
            return self._materialize_bundle(
                source_id=source_id,
                request_bbox=request_bbox,
                resolved_aoi=resolved_aoi,
                target_dir=target_dir,
                target_crs=target_crs,
                data_requirements=data_requirements,
            )
        except BundleMaterializationError as exc:
            combined_coverage.update(exc.component_coverage)
            combined_provider_attempts.extend(exc.provider_attempts)

        for fallback_source_id in source_fallback_candidates(
            source_id,
            policy_registry=self.policy_registry,
        ):
            attempted_sources.append(fallback_source_id)
            if target_dir.exists():
                shutil.rmtree(target_dir)
            try:
                fallback = self._materialize_bundle(
                    source_id=fallback_source_id,
                    request_bbox=request_bbox,
                    resolved_aoi=resolved_aoi,
                    target_dir=target_dir,
                    target_crs=target_crs,
                    data_requirements=data_requirements,
                )
            except BundleMaterializationError as exc:
                combined_coverage.update(exc.component_coverage)
                combined_provider_attempts.extend(exc.provider_attempts)
                continue
            combined_coverage.update(fallback.component_coverage)
            combined_provider_attempts.extend(fallback.provider_attempts)
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

        raise BundleMaterializationError(
            f"AOI-scoped bundle did not satisfy its KG completeness contract for {source_id}",
            component_coverage=combined_coverage,
            provider_attempts=self._renumber_provider_attempts(combined_provider_attempts),
        )

    def _materialize_bundle(
        self,
        *,
        source_id: str,
        request_bbox: Optional[BBox],
        resolved_aoi: ResolvedAOI | None = None,
        target_dir: Path,
        target_crs: str,
        data_requirements: DataRequirementPlan | None,
    ) -> MaterializedInputBundle:
        spec = self._spec_for(source_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        policy_candidates = self._candidate_source_ids(
            source_id=source_id,
            data_requirements=data_requirements,
        )
        if not policy_candidates:
            raise BundleMaterializationError(
                f"KG bundle policy has no executable component candidates for {source_id}"
            )
        return self._materialize_policy_candidate_bundle(
            spec=spec,
            source_id=source_id,
            candidates=policy_candidates,
            request_bbox=request_bbox,
            resolved_aoi=resolved_aoi,
            target_dir=target_dir,
            target_crs=target_crs,
            data_requirements=data_requirements,
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
        data_requirements: DataRequirementPlan | None,
    ) -> MaterializedInputBundle:
        resolved_components: dict[str, MaterializedRawVectorSource] = {}
        component_coverage: dict[str, object] = {}
        provider_attempts: list[dict[str, object]] = []
        role_contracts_by_source = self._role_contracts_by_source(
            source_id=source_id,
            data_requirements=data_requirements,
        )

        for component_source_id in candidates:
            target_path = target_dir / "components" / f"{component_source_id.replace('.', '_')}.zip"
            role_contracts = role_contracts_by_source.get(component_source_id, ())
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
                component_coverage[component_source_id] = self._source_coverage_status(
                    source_id=component_source_id,
                    source_mode=source_mode,
                    feature_count=0,
                    coverage_status=coverage_status,
                    path=None,
                    error=str(exc),
                    fault_class=fault_class,
                    external_uncontrollable=fault_class in EXTERNAL_UNCONTROLLABLE_FAULTS,
                    role_contracts=role_contracts,
                )
                provider_attempts.append(
                    self._decorate_attempt_with_roles(
                        build_source_attempt(
                            source_id=component_source_id,
                            status=coverage_status if fault_class == "CONFIG_MISSING" else "failed",
                            fault_class=fault_class,
                            fault_message=str(exc),
                            attempt_no=len(provider_attempts) + 1,
                            recoverable=False if fault_class == "CONFIG_MISSING" else None,
                        ),
                        role_contracts,
                    )
                )
                continue

            resolved_components[component_source_id] = resolved
            coverage_status = coverage_status_for_count(resolved.feature_count)
            if coverage_status == "empty":
                coverage_status = self.policy_registry.empty_coverage_status(
                    component_source_id
                )
            component_coverage[component_source_id] = self._source_coverage_status(
                source_id=component_source_id,
                source_mode=resolved.source_mode,
                feature_count=resolved.feature_count,
                coverage_status=coverage_status,
                path=resolved.zip_path,
                role_contracts=role_contracts,
            )
            provider_attempts.append(
                self._decorate_attempt_with_roles(
                    build_success_attempt(
                        source_id=component_source_id,
                        status="available" if coverage_status == "available" else "empty",
                        attempt_no=len(provider_attempts) + 1,
                        coverage_status=coverage_status,
                        feature_count=resolved.feature_count,
                        selected_for_fusion=False,
                    ),
                    role_contracts,
                )
            )

        height_source_ids = self._height_source_ids(data_requirements)
        if self._is_building_catalog(source_id) and self.raster_height_source_service is not None and height_source_ids:
            raster_coverage, raster_attempts = self.raster_height_source_service.materialize_preferred(
                target_dir=target_dir / "height_rasters",
                request_bbox=request_bbox,
                resolved_aoi=resolved_aoi,
                source_ids=height_source_ids,
                starting_attempt_no=len(provider_attempts) + 1,
            )
            for raster_source_id, coverage in raster_coverage.items():
                contracts = role_contracts_by_source.get(raster_source_id, ())
                if contracts:
                    coverage.update(self._role_evidence_payload(contracts))
            for attempt in raster_attempts:
                contracts = role_contracts_by_source.get(str(attempt.get("source_id") or ""), ())
                if contracts:
                    attempt.update(self._role_evidence_payload(contracts))
            component_coverage.update(raster_coverage)
            provider_attempts.extend(raster_attempts)

        selected_role_sources = self._select_role_sources(
            data_requirements=data_requirements,
            resolved_components=resolved_components,
            component_coverage=component_coverage,
            provider_attempts=provider_attempts,
        )
        self._validate_full_closure(
            source_id=source_id,
            component_coverage=component_coverage,
            provider_attempts=provider_attempts,
        )
        if data_requirements is None and not any(
            _coverage_is_non_empty(status) for status in component_coverage.values()
        ):
            raise BundleMaterializationError(
                f"AOI-scoped bundle has empty source coverage for {source_id}",
                component_coverage=component_coverage,
                provider_attempts=provider_attempts,
            )

        primary_source_id, reference_source_id = self._output_source_ids(
            spec=spec,
            data_requirements=data_requirements,
            selected_role_sources=selected_role_sources,
            resolved_components=resolved_components,
        )
        primary_component = resolved_components.get(primary_source_id or "")
        if primary_component is None:
            raise BundleMaterializationError(
                f"KG role selection produced no primary materialized component for {source_id}",
                component_coverage=component_coverage,
                provider_attempts=provider_attempts,
            )
        osm = self._ensure_component_zip_path(
            component=primary_component,
            output_zip=target_dir / "osm.zip",
        )
        reference_component = resolved_components.get(reference_source_id or "")
        ref = (
            self._ensure_component_zip_path(
                component=reference_component,
                output_zip=target_dir / "ref.zip",
            )
            if reference_component is not None
            else None
        )
        if ref is None:
            ref = self._create_empty_reference_bundle(
                osm=osm,
                output_zip=target_dir / "ref.zip",
                source_id=reference_source_id or spec.ref_source_id or "ref",
                source_mode="missing_optional_ref",
            )

        selected_roles_by_source: dict[str, list[str]] = {}
        for role_id, selected_source_id in selected_role_sources.items():
            if selected_source_id:
                selected_roles_by_source.setdefault(selected_source_id, []).append(role_id)
        for component_source_id, coverage in list(component_coverage.items()):
            selected_role_ids = tuple(selected_roles_by_source.get(component_source_id, ()))
            if isinstance(coverage, RoleAwareSourceCoverageStatus):
                component_coverage[component_source_id] = replace(
                    coverage,
                    selected_role_ids=selected_role_ids,
                )
            elif isinstance(coverage, dict) and selected_role_ids:
                coverage["selected_role_ids"] = list(selected_role_ids)
        if data_requirements is not None:
            for attempt in provider_attempts:
                selected_role_ids = selected_roles_by_source.get(str(attempt.get("source_id") or ""), [])
                attempt["selected_for_fusion"] = bool(selected_role_ids)
                if selected_role_ids:
                    attempt["selected_role_ids"] = list(selected_role_ids)

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

    def _candidate_source_ids(
        self,
        *,
        source_id: str,
        data_requirements: DataRequirementPlan | None,
    ) -> list[str]:
        bundle_candidates = source_component_candidates(
            source_id,
            (),
            policy_registry=self.policy_registry,
        )
        if data_requirements is None:
            return bundle_candidates

        allowed = set(bundle_candidates)
        role_candidates = [
            candidate.source_id
            for role in data_requirements.roles
            if not self._role_is_raster(role)
            for candidate in self._sorted_role_candidates(role)
            if candidate.source_id in allowed
        ]
        closure_candidates = [
            candidate_source_id
            for candidate_source_id in self._required_full_closure_source_ids(source_id)
            if candidate_source_id in allowed
        ]
        return _unique_preserving_order([*role_candidates, *closure_candidates])

    @staticmethod
    def _height_source_ids(data_requirements: DataRequirementPlan | None) -> list[str]:
        if data_requirements is None:
            return list(BUILDING_HEIGHT_RASTER_PRIORITY_ORDER)
        supported = set(BUILDING_HEIGHT_RASTER_PRIORITY_ORDER)
        return _unique_preserving_order(
            candidate.source_id
            for role in data_requirements.roles
            if LocalBundleCatalogProvider._role_is_raster(role)
            for candidate in LocalBundleCatalogProvider._sorted_role_candidates(role)
            if candidate.source_id in supported
        )

    def _role_contracts_by_source(
        self,
        *,
        source_id: str,
        data_requirements: DataRequirementPlan | None,
    ) -> dict[str, tuple[dict[str, object], ...]]:
        if data_requirements is None:
            return {}
        contracts: dict[str, list[dict[str, object]]] = {}
        for role in data_requirements.roles:
            payload = role.model_dump(mode="json")
            for candidate in role.candidates:
                contracts.setdefault(candidate.source_id, []).append(payload)
        for closure_source_id in self._required_full_closure_source_ids(source_id):
            if closure_source_id in contracts:
                continue
            raise KnowledgeReleaseError(
                "Data requirement plan is missing a required source-role binding for "
                f"bundle {source_id}: {closure_source_id}"
            )
        return {key: tuple(value) for key, value in contracts.items()}

    @staticmethod
    def _source_coverage_status(
        *,
        source_id: str,
        source_mode: str,
        feature_count: int | None,
        coverage_status: str,
        path: Path | None = None,
        error: str | None = None,
        fault_class: str | None = None,
        external_uncontrollable: bool = False,
        role_contracts: tuple[dict[str, object], ...] = (),
    ) -> SourceCoverageStatus:
        common = {
            "source_id": source_id,
            "source_mode": source_mode,
            "feature_count": feature_count,
            "coverage_status": coverage_status,
            "path": path,
            "error": error,
            "fault_class": fault_class,
            "external_uncontrollable": external_uncontrollable,
        }
        if not role_contracts:
            return SourceCoverageStatus(**common)
        evidence = LocalBundleCatalogProvider._role_evidence_payload(role_contracts)
        return RoleAwareSourceCoverageStatus(
            **common,
            role_id=str(evidence["role_id"]),
            role_ids=tuple(str(item) for item in evidence["role_ids"]),
            role_contract=dict(evidence["role_contract"]),
            role_contracts=tuple(dict(item) for item in evidence["role_contracts"]),
        )

    @staticmethod
    def _role_evidence_payload(
        role_contracts: tuple[dict[str, object], ...],
    ) -> dict[str, object]:
        role_ids = [str(contract.get("role_id") or "") for contract in role_contracts]
        return {
            "role_id": role_ids[0],
            "role_ids": role_ids,
            "role_contract": dict(role_contracts[0]),
            "role_contracts": [dict(contract) for contract in role_contracts],
        }

    @staticmethod
    def _decorate_attempt_with_roles(
        attempt: dict[str, object],
        role_contracts: tuple[dict[str, object], ...],
    ) -> dict[str, object]:
        if role_contracts:
            attempt.update(LocalBundleCatalogProvider._role_evidence_payload(role_contracts))
        return attempt

    def _select_role_sources(
        self,
        *,
        data_requirements: DataRequirementPlan | None,
        resolved_components: dict[str, MaterializedRawVectorSource],
        component_coverage: dict[str, object],
        provider_attempts: list[dict[str, object]],
    ) -> dict[str, str | None]:
        if data_requirements is None:
            return {}
        selected: dict[str, str | None] = {}
        for role in data_requirements.roles:
            selected_source_id: str | None = None
            distinct_source_ids = {
                selected[role_id]
                for role_id in role.distinct_from_role_ids
                if role_id in selected and selected[role_id] is not None
            }
            for candidate in self._sorted_role_candidates(role):
                candidate_source_id = candidate.source_id
                if candidate_source_id in distinct_source_ids:
                    continue
                coverage = component_coverage.get(candidate_source_id)
                if coverage is None:
                    continue
                if role.completeness_policy == CompletenessPolicy.required_query_with_sparse_allowed:
                    query_succeeded = candidate_source_id in resolved_components or _coverage_status_value(coverage) == "available"
                    if query_succeeded:
                        selected_source_id = candidate_source_id
                        break
                elif _coverage_is_non_empty(coverage):
                    selected_source_id = candidate_source_id
                    break
            selected[role.role_id] = selected_source_id
            if role.required and selected_source_id is None:
                raise BundleMaterializationError(
                    f"required role {role.role_id} did not satisfy {role.completeness_policy.value}",
                    component_coverage=component_coverage,
                    provider_attempts=provider_attempts,
                )
        return selected

    def _validate_full_closure(
        self,
        *,
        source_id: str,
        component_coverage: dict[str, object],
        provider_attempts: list[dict[str, object]],
    ) -> None:
        if not self._requires_complete_pair_coverage(source_id):
            return
        missing_source_ids = [
            component_source_id
            for component_source_id in self._required_full_closure_source_ids(source_id)
            if not _coverage_is_non_empty(component_coverage.get(component_source_id))
        ]
        if missing_source_ids:
            raise BundleMaterializationError(
                "required full closure is incomplete for "
                f"{source_id}: {', '.join(missing_source_ids)}",
                component_coverage=component_coverage,
                provider_attempts=provider_attempts,
            )

    @staticmethod
    def _output_source_ids(
        *,
        spec: CatalogBundleSpec,
        data_requirements: DataRequirementPlan | None,
        selected_role_sources: dict[str, str | None],
        resolved_components: dict[str, MaterializedRawVectorSource],
    ) -> tuple[str | None, str | None]:
        if data_requirements is not None:
            vector_roles = [role for role in data_requirements.roles if not LocalBundleCatalogProvider._role_is_raster(role)]
            primary_roles = [role for role in vector_roles if role.bundle_slot == BundleSlot.primary]
            reference_roles = [role for role in vector_roles if role.bundle_slot == BundleSlot.reference]
            if len(primary_roles) != 1:
                raise BundleMaterializationError(
                    "KG data requirement plan must contain exactly one vector primary bundle slot"
                )
            if len(reference_roles) > 1:
                raise BundleMaterializationError(
                    "KG data requirement plan must contain at most one vector reference bundle slot"
                )
            primary_source_id = selected_role_sources.get(primary_roles[0].role_id)
            reference_source_id = (
                selected_role_sources.get(reference_roles[0].role_id)
                if reference_roles
                else None
            )
            return primary_source_id, reference_source_id

        primary_source_id = spec.osm_source_id if spec.osm_source_id in resolved_components else next(
            iter(resolved_components),
            None,
        )
        reference_source_id = None
        if spec.ref_source_id and spec.ref_source_id in resolved_components:
            reference_source_id = spec.ref_source_id
        if reference_source_id is None:
            reference_source_id = next(
                (
                    component_source_id
                    for component_source_id, component in resolved_components.items()
                    if component_source_id != primary_source_id and _materialized_source_is_non_empty(component)
                ),
                None,
            )
        return primary_source_id, reference_source_id

    @staticmethod
    def _role_is_raster(role: SourceRoleRequirement) -> bool:
        return any(str(geometry_type).casefold() == "raster" for geometry_type in role.geometry_types)

    @staticmethod
    def _sorted_role_candidates(role: SourceRoleRequirement):
        return sorted(role.candidates, key=lambda candidate: (candidate.priority, candidate.source_id))

    @staticmethod
    def _is_building_catalog(source_id: str) -> bool:
        return source_id in {"catalog.flood.building", "catalog.earthquake.building"}

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

    def _source_attempt_fault(self, source_id: str, exc: Exception) -> tuple[str, str]:
        del source_id
        fault_class = classify_failure_category(
            str(exc),
            scope="source_acquisition",
            error_type=type(exc).__name__,
            policy_registry=self.policy_registry,
        )
        return self.policy_registry.source_mode_for_fault(fault_class), fault_class

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

    def _requires_complete_pair_coverage(self, source_id: str) -> bool:
        return requires_complete_pair_coverage(
            source_id,
            policy_registry=self.policy_registry,
        )

    def _required_full_closure_source_ids(self, source_id: str) -> list[str]:
        return required_full_closure_source_ids(
            source_id,
            policy_registry=self.policy_registry,
        )

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


def _coverage_status_value(status: object) -> str:
    if isinstance(status, dict):
        value = status.get("coverage_status")
    else:
        value = getattr(status, "coverage_status", None)
    return str(value or "").strip().casefold()


def _coverage_is_non_empty(status: object) -> bool:
    if status is None:
        return False
    if _coverage_feature_count(status) > 0:
        return True
    if isinstance(status, dict):
        feature_count = status.get("feature_count")
    else:
        feature_count = getattr(status, "feature_count", None)
    return feature_count is None and _coverage_status_value(status) == "available"


def _materialized_source_is_non_empty(source: MaterializedRawVectorSource | None) -> bool:
    return bool(source is not None and (source.feature_count or 0) > 0)


def _unique_preserving_order(values) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result
