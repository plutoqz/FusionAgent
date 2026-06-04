from __future__ import annotations

from schemas.data_requirement import CompletenessPolicy, SourceCandidate, SourceRoleRequirement


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
