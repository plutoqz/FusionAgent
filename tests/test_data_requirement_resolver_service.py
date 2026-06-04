from __future__ import annotations

from schemas.agent import RunTrigger, RunTriggerType, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from schemas.data_requirement import CompletenessPolicy, SourceCandidate, SourceRoleRequirement
from schemas.task_kind import TaskKind
from services.data_requirement_resolver_service import DataRequirementResolverService


def test_source_role_requirement_serializes_candidate_order() -> None:
    requirement = SourceRoleRequirement(
        role_id="primary_footprint",
        required=True,
        geometry_types=["Polygon", "MultiPolygon"],
        completeness_policy=CompletenessPolicy.required_non_empty,
        candidates=[
            SourceCandidate(source_id="raw.osm.building", provider_family="osm", priority=10),
            SourceCandidate(source_id="raw.microsoft.building", provider_family="microsoft", priority=20),
        ],
    )

    payload = requirement.model_dump(mode="json")

    assert payload["role_id"] == "primary_footprint"
    assert payload["completeness_policy"] == "required_non_empty"
    assert [item["source_id"] for item in payload["candidates"]] == [
        "raw.osm.building",
        "raw.microsoft.building",
    ]


def _plan(*, algorithm_id: str, output_type: str) -> WorkflowPlan:
    return WorkflowPlan(
        workflow_id="wf-test",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="test"),
        context={"retrieval": {"candidate_patterns": [{"pattern_id": "wp.test"}]}},
        tasks=[
            WorkflowTask(
                step=1,
                name="fusion",
                description="fusion",
                algorithm_id=algorithm_id,
                input=WorkflowTaskInput(data_type_id="dt.input", data_source_id="catalog.test"),
                output=WorkflowTaskOutput(data_type_id=output_type),
                kg_validated=True,
            )
        ],
        expected_output="out",
    )


def test_resolver_building_without_height_uses_footprint_roles() -> None:
    result = DataRequirementResolverService().resolve(
        task_kind=TaskKind.building,
        plan=_plan(algorithm_id="algo.fusion.building.v1", output_type="dt.building.fused"),
        mission_requirements={},
    )

    assert [role.role_id for role in result.roles] == ["primary_footprint", "reference_footprint"]
    primary = result.roles[0]
    assert [candidate.source_id for candidate in primary.candidates] == [
        "raw.osm.building",
        "raw.google.building",
        "raw.microsoft.building",
    ]
    assert all(role.completeness_policy.value == "required_non_empty" for role in result.roles)


def test_resolver_building_height_adds_height_signal_role_only_when_requested() -> None:
    result = DataRequirementResolverService().resolve(
        task_kind=TaskKind.building,
        plan=_plan(algorithm_id="algo.fusion.building.height_enriched.v1", output_type="dt.building.fused"),
        mission_requirements={"building_height": True},
    )

    assert [role.role_id for role in result.roles] == [
        "primary_footprint",
        "reference_footprint",
        "height_signal",
    ]
    assert result.roles[2].completeness_policy.value == "optional_when_requirement_absent"


def test_resolver_distinguishes_water_polygon_and_waterways() -> None:
    resolver = DataRequirementResolverService()

    polygon = resolver.resolve(
        task_kind=TaskKind.water_polygon,
        plan=_plan(algorithm_id="algo.fusion.water_polygon.priority_merge.v2", output_type="dt.water.fused"),
    )
    waterways = resolver.resolve(
        task_kind=TaskKind.waterways,
        plan=_plan(algorithm_id="algo.fusion.waterways.conflation.v7", output_type="dt.waterways.fused"),
    )

    assert polygon.roles[0].geometry_types == ["Polygon", "MultiPolygon"]
    assert waterways.roles[0].geometry_types == ["LineString", "MultiLineString"]
    assert "raw.hydrolakes.water" in [candidate.source_id for candidate in polygon.roles[1].candidates]
    assert "raw.hydrorivers.water" in [candidate.source_id for candidate in waterways.roles[1].candidates]
