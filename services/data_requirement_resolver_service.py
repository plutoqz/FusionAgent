from __future__ import annotations

from typing import Any

from schemas.agent import WorkflowPlan
from schemas.data_requirement import CompletenessPolicy, DataRequirementPlan, SourceCandidate, SourceRoleRequirement
from schemas.task_kind import TaskKind, task_kind_family


class DataRequirementResolverService:
    def resolve(
        self,
        *,
        task_kind: TaskKind,
        plan: WorkflowPlan,
        mission_requirements: dict[str, Any] | None = None,
    ) -> DataRequirementPlan:
        algorithm_id = _selected_algorithm_id(plan)
        output_data_type = _selected_output_type(plan)
        mission_requirements = dict(mission_requirements or {})
        roles = _ROLE_BUILDERS[task_kind](mission_requirements, algorithm_id)
        evidence = {
            "resolver_version": "2026-06-29.v2",
            "basis": "task_kind_and_selected_algorithm",
            "workflow_id": plan.workflow_id,
        }
        if task_kind == TaskKind.building:
            evidence["building_height_policy"] = {
                "height_required": False,
                "preferred_order": [
                    "raw.google.open_buildings_2_5d.height_raster",
                    "raw.3d_globfp.building_height.raster",
                    "raw.google.building_height.raster",
                    "raw.local.building_height.raster",
                ],
                "rapid_response_fallback": [
                    "raw.osm.building",
                    "raw.google.building",
                    "raw.microsoft.building",
                ],
                "degradation_mode": "fallback_to_footprint_fusion_without_height",
            }
        if task_kind == TaskKind.road:
            evidence["road_name_policy"] = {
                "required": True,
                "primary_source": "raw.osm.road",
                "preserve_fields": ["name", "osm_name", "road_name", "ref"],
            }
        return DataRequirementPlan(
            task_kind=task_kind,
            task_family=task_kind_family(task_kind),
            algorithm_id=algorithm_id,
            output_data_type=output_data_type,
            roles=roles,
            evidence=evidence,
        )


def _selected_algorithm_id(plan: WorkflowPlan) -> str | None:
    for task in plan.tasks:
        if not task.is_transform:
            return task.algorithm_id
    return None


def _selected_output_type(plan: WorkflowPlan) -> str | None:
    for task in plan.tasks:
        if not task.is_transform:
            return task.output.data_type_id
    return None


def _candidate(source_id: str, provider_family: str, priority: int) -> SourceCandidate:
    return SourceCandidate(source_id=source_id, provider_family=provider_family, priority=priority)


def _building_roles(requirements: dict[str, Any], algorithm_id: str | None) -> list[SourceRoleRequirement]:
    roles = [
        SourceRoleRequirement(
            role_id="primary_footprint",
            geometry_types=["Polygon", "MultiPolygon"],
            completeness_policy=CompletenessPolicy.required_non_empty,
            candidates=[
                _candidate("raw.osm.building", "osm", 10),
                _candidate("raw.google.building", "google", 20),
                _candidate("raw.microsoft.building", "microsoft", 30),
            ],
        ),
        SourceRoleRequirement(
            role_id="reference_footprint",
            geometry_types=["Polygon", "MultiPolygon"],
            completeness_policy=CompletenessPolicy.required_non_empty,
            candidates=[
                _candidate("raw.microsoft.building", "microsoft", 10),
                _candidate("raw.google.building", "google", 20),
                _candidate("raw.osm.building", "osm", 30),
            ],
        ),
    ]
    height_required = bool(requirements.get("building_height_required"))
    roles.append(
        SourceRoleRequirement(
            role_id="height_signal",
            required=height_required,
            geometry_types=["Raster"],
            completeness_policy=CompletenessPolicy.optional_when_requirement_absent,
            candidates=[
                _candidate("raw.google.open_buildings_2_5d.height_raster", "google_open_buildings_2_5d", 10),
                _candidate("raw.3d_globfp.building_height.raster", "3d_globfp", 20),
                _candidate("raw.google.building_height.raster", "google_temporal", 30),
                _candidate("raw.local.building_height.raster", "local", 40),
            ],
        )
    )
    if "height" in str(algorithm_id or "").casefold() and not height_required:
        roles[-1].fallback_role_ids.append("primary_footprint")
    return roles


def _road_roles(_requirements: dict[str, Any], _algorithm_id: str | None) -> list[SourceRoleRequirement]:
    return [
        SourceRoleRequirement(
            role_id="base_network",
            geometry_types=["LineString", "MultiLineString"],
            completeness_policy=CompletenessPolicy.required_non_empty,
            candidates=[_candidate("raw.osm.road", "osm", 10)],
        ),
        SourceRoleRequirement(
            role_id="reference_network",
            geometry_types=["LineString", "MultiLineString"],
            completeness_policy=CompletenessPolicy.optional_reference,
            candidates=[
                _candidate("raw.overture.transportation", "overture", 10),
                _candidate("raw.overture.road", "overture", 20),
            ],
        ),
    ]


def _water_polygon_roles(_requirements: dict[str, Any], _algorithm_id: str | None) -> list[SourceRoleRequirement]:
    return [
        SourceRoleRequirement(
            role_id="base_water_polygon",
            geometry_types=["Polygon", "MultiPolygon"],
            completeness_policy=CompletenessPolicy.required_query_with_sparse_allowed,
            candidates=[_candidate("raw.osm.water", "osm", 10)],
        ),
        SourceRoleRequirement(
            role_id="reference_water_polygon",
            geometry_types=["Polygon", "MultiPolygon"],
            completeness_policy=CompletenessPolicy.optional_reference,
            candidates=[_candidate("raw.hydrolakes.water", "hydrosheds", 10)],
        ),
    ]


def _waterways_roles(_requirements: dict[str, Any], _algorithm_id: str | None) -> list[SourceRoleRequirement]:
    return [
        SourceRoleRequirement(
            role_id="base_waterway_line",
            geometry_types=["LineString", "MultiLineString"],
            completeness_policy=CompletenessPolicy.required_query_with_sparse_allowed,
            candidates=[_candidate("raw.osm.waterways", "osm", 10)],
        ),
        SourceRoleRequirement(
            role_id="reference_river_line",
            geometry_types=["LineString", "MultiLineString"],
            completeness_policy=CompletenessPolicy.optional_reference,
            candidates=[
                _candidate("raw.hydrorivers.water", "hydrosheds", 10),
                _candidate("raw.local.pakistan.waterways", "local", 20),
            ],
        ),
    ]


def _poi_roles(_requirements: dict[str, Any], _algorithm_id: str | None) -> list[SourceRoleRequirement]:
    return [
        SourceRoleRequirement(
            role_id="base_poi",
            geometry_types=["Point", "MultiPoint"],
            completeness_policy=CompletenessPolicy.required_query_with_sparse_allowed,
            candidates=[_candidate("raw.osm.poi", "osm", 10)],
        ),
        SourceRoleRequirement(
            role_id="reference_poi",
            geometry_types=["Point", "MultiPoint"],
            completeness_policy=CompletenessPolicy.optional_reference,
            candidates=[_candidate("raw.gns.poi", "gns", 10)],
        ),
    ]


_ROLE_BUILDERS = {
    TaskKind.building: _building_roles,
    TaskKind.road: _road_roles,
    TaskKind.water_polygon: _water_polygon_roles,
    TaskKind.waterways: _waterways_roles,
    TaskKind.poi: _poi_roles,
}
