from __future__ import annotations

from enum import Enum


class ArtifactRole(str, Enum):
    raw_source = "raw_source"
    input_bundle = "input_bundle"
    intermediate = "intermediate"
    fusion_result = "fusion_result"
    compat_export = "compat_export"
    quality_report = "quality_report"
    evidence_package = "evidence_package"


_ALIASES = {
    "raw_vector": ArtifactRole.raw_source.value,
    "raw-source": ArtifactRole.raw_source.value,
    "input-bundle": ArtifactRole.input_bundle.value,
    "fusion-result": ArtifactRole.fusion_result.value,
}


def normalize_artifact_role(value: object | None) -> str | None:
    if value is None:
        return None
    if hasattr(value, "value"):
        value = getattr(value, "value")
    token = str(value).strip()
    if not token:
        return None
    token = token.replace(" ", "_").casefold()
    token = _ALIASES.get(token, token)
    allowed = {role.value for role in ArtifactRole}
    return token if token in allowed else None
