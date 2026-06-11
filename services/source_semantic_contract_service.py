from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from kg.track_b_source_contract import get_track_b_source_contract
from services.source_field_profile_registry import SourceFieldProfileRegistry
from services.source_profile_service import SourceProfile, SourceProfileService


@dataclass(frozen=True)
class MatchedField:
    canonical_field: str
    meaning: str
    required: bool
    candidate_fields: list[str]
    matched_field: str | None
    available: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceSemanticEntry:
    source_id: str
    source_name: str
    field_mapping_profile: str
    source_form: str
    artifact_path: str
    crs: str | None
    feature_count: int | None
    field_names: list[str]
    height_fields: list[str]
    height_semantics: str
    matched_fields: dict[str, MatchedField]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["matched_fields"] = {key: value.to_dict() for key, value in self.matched_fields.items()}
        return payload


@dataclass(frozen=True)
class SourceSemanticContract:
    run_id: str
    job_type: str
    selected_source_id: str
    target_crs: str
    component_source_ids: list[str]
    sources: dict[str, SourceSemanticEntry]
    height_policy: dict[str, Any] = field(default_factory=dict)
    parameter_hints: dict[str, Any] = field(default_factory=dict)
    validation: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "job_type": self.job_type,
            "selected_source_id": self.selected_source_id,
            "target_crs": self.target_crs,
            "component_source_ids": list(self.component_source_ids),
            "sources": {key: value.to_dict() for key, value in self.sources.items()},
            "height_policy": dict(self.height_policy),
            "parameter_hints": dict(self.parameter_hints),
            "validation": dict(self.validation),
            "metadata": dict(self.metadata),
        }


class SourceSemanticContractService:
    def __init__(
        self,
        *,
        kg_repo: Any,
        profile_service: SourceProfileService | None = None,
        registry: SourceFieldProfileRegistry | None = None,
    ) -> None:
        self.kg_repo = kg_repo
        self.profile_service = profile_service or SourceProfileService()
        self.registry = registry or SourceFieldProfileRegistry()

    def build_contract(
        self,
        *,
        run_id: str,
        job_type: str,
        selected_source_id: str,
        component_paths: dict[str, Path],
        target_crs: str,
        raster_paths: dict[str, Path] | None = None,
    ) -> SourceSemanticContract:
        data_sources = self._data_sources_by_id()
        sources: dict[str, SourceSemanticEntry] = {}
        issues: list[dict[str, str]] = []
        vector_height_fields: dict[str, str] = {}

        for source_id, raw_path in component_paths.items():
            path = Path(raw_path)
            node = data_sources.get(source_id)
            track_b_contract = get_track_b_source_contract(source_id)
            profile_id = (
                track_b_contract.field_mapping_profile
                if track_b_contract is not None
                else str((getattr(node, "metadata", {}) or {}).get("field_mapping_profile") or "")
            )
            if not profile_id:
                profile_id = self.registry.profile_ids_for_theme(job_type)[0]
            field_profile = self.registry.get(profile_id)

            metadata = dict(getattr(node, "metadata", {}) or {})
            if track_b_contract is not None:
                metadata.update(
                    {
                        "track_b_role": track_b_contract.role,
                        "acquisition_class": track_b_contract.acquisition_class,
                        "clip_strategy": track_b_contract.clip_strategy,
                        "runtime_status": track_b_contract.runtime_status,
                        "license_boundary": track_b_contract.license_boundary,
                    }
                )
            profile = self.profile_service.profile_vector_source(
                source_id=source_id,
                path=path,
                source_name=getattr(node, "source_name", source_id),
                runtime_status=str(metadata.get("runtime_status") or "runtime_candidate"),
                selectable_now=bool(metadata.get("selectable_now", True)),
                metadata=metadata,
            )
            matched_fields = self._match_fields(profile=profile, profile_id=profile_id)
            for canonical, matched in matched_fields.items():
                if matched.required and not matched.available:
                    issues.append(
                        {
                            "source_id": source_id,
                            "canonical_field": canonical,
                            "code": "required_field_unmatched",
                        }
                    )
            height_match = matched_fields.get("height_m")
            if height_match is not None and height_match.matched_field:
                vector_height_fields[source_id] = height_match.matched_field

            sources[source_id] = SourceSemanticEntry(
                source_id=source_id,
                source_name=getattr(node, "source_name", source_id),
                field_mapping_profile=profile_id,
                source_form=profile.source_form,
                artifact_path=profile.canonical_path,
                crs=profile.crs,
                feature_count=profile.feature_count,
                field_names=profile.field_names,
                height_fields=profile.height_fields,
                height_semantics=profile.height_semantics,
                matched_fields=matched_fields,
                metadata=metadata,
            )

        raster_height_sources: dict[str, str] = {}
        for source_id, raw_path in (raster_paths or {}).items():
            path = Path(raw_path)
            if not path.exists():
                continue
            node = data_sources.get(source_id)
            profile = self.profile_service.profile_raster_source(
                source_id=source_id,
                path=path,
                source_name=getattr(node, "source_name", source_id),
                runtime_status=str((getattr(node, "metadata", {}) or {}).get("runtime_status") or "runtime_candidate"),
                selectable_now=bool((getattr(node, "metadata", {}) or {}).get("selectable_now", True)),
                metadata=dict(getattr(node, "metadata", {}) or {}),
            )
            if profile.height_semantics == "estimated_height":
                raster_height_sources[source_id] = profile.canonical_path

        height_policy = self._height_policy(
            job_type=job_type,
            vector_height_fields=vector_height_fields,
            raster_height_sources=raster_height_sources,
        )
        parameter_hints = self._parameter_hints(
            job_type=job_type,
            component_source_ids=list(component_paths.keys()),
        )
        return SourceSemanticContract(
            run_id=run_id,
            job_type=job_type,
            selected_source_id=selected_source_id,
            target_crs=target_crs,
            component_source_ids=list(component_paths.keys()),
            sources=sources,
            height_policy=height_policy,
            parameter_hints=parameter_hints,
            validation={"valid": not issues, "issues": issues},
            metadata={},
        )

    def _match_fields(self, *, profile: SourceProfile, profile_id: str) -> dict[str, MatchedField]:
        field_profile = self.registry.get(profile_id)
        available_by_casefold = {field.casefold(): field for field in profile.field_names}
        matched: dict[str, MatchedField] = {}
        for canonical, canonical_spec in field_profile.canonical_fields.items():
            candidates = list(field_profile.provider_probe_order.get(canonical, []))
            matched_field = None
            for candidate in candidates:
                if candidate in profile.field_names:
                    matched_field = candidate
                    break
                normalized_candidate = candidate.casefold()
                if normalized_candidate in available_by_casefold:
                    matched_field = available_by_casefold[normalized_candidate]
                    break
            matched[canonical] = MatchedField(
                canonical_field=canonical,
                meaning=canonical_spec.meaning,
                required=canonical_spec.required,
                candidate_fields=candidates,
                matched_field=matched_field,
                available=matched_field is not None,
            )
        return matched

    def _data_sources_by_id(self) -> dict[str, Any]:
        list_data_sources = getattr(self.kg_repo, "list_data_sources", None)
        if not callable(list_data_sources):
            return {}
        return {source.source_id: source for source in list_data_sources()}

    @staticmethod
    def _height_policy(
        *,
        job_type: str,
        vector_height_fields: dict[str, str],
        raster_height_sources: dict[str, str],
    ) -> dict[str, Any]:
        if job_type != "building":
            return {}
        return {
            "height_output_field": "height_raster",
            "canonical_height_field": "height",
            "positive_only": True,
            "vector_height_fields": dict(vector_height_fields),
            "raster_height_sources": dict(raster_height_sources),
        }

    @staticmethod
    def _parameter_hints(*, job_type: str, component_source_ids: list[str]) -> dict[str, Any]:
        if job_type == "building":
            alias_by_source = {
                "raw.microsoft.building": "MS",
                "raw.local.microsoft.building": "MICROSOFT_LOCAL",
                "raw.openbuildingmap.building": "OBM",
                "raw.google.open_buildings.vector": "GOOGLE_OPEN_BUILDINGS",
                "raw.google.building": "GOOGLE",
                "raw.osm.building": "OSM",
            }
            priority = [alias_by_source[item] for item in component_source_ids if item in alias_by_source]
            return {"source_priority_order": priority} if priority else {}
        if job_type == "poi":
            return {"geohash_precision": 8}
        return {}
