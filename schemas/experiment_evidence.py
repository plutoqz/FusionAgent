from __future__ import annotations

from pydantic import BaseModel, Field


class FrozenFileHash(BaseModel):
    relative_path: str
    sha256: str
    size_bytes: int


class ExperimentEvidenceManifest(BaseModel):
    experiment_id: str
    output_dir: str
    commit_sha: str
    seed_hash: str
    runtime_settings_hash: str
    metric_definition_hash: str
    files: list[FrozenFileHash] = Field(default_factory=list)
