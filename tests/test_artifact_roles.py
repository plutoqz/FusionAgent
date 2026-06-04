from __future__ import annotations

from schemas.artifact_role import ArtifactRole, normalize_artifact_role


def test_artifact_role_vocab_has_engineering_contract_values() -> None:
    assert [role.value for role in ArtifactRole] == [
        "raw_source",
        "input_bundle",
        "intermediate",
        "fusion_result",
        "compat_export",
        "quality_report",
        "evidence_package",
    ]


def test_normalize_artifact_role_keeps_legacy_raw_vector_compatible() -> None:
    assert normalize_artifact_role("raw_vector") == ArtifactRole.raw_source.value
    assert normalize_artifact_role("raw_source") == ArtifactRole.raw_source.value
    assert normalize_artifact_role(ArtifactRole.fusion_result) == ArtifactRole.fusion_result.value
    assert normalize_artifact_role("unknown") is None
