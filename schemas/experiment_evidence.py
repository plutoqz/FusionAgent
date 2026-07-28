from __future__ import annotations

from pydantic import BaseModel, Field


class FrozenFileHash(BaseModel):
    relative_path: str
    sha256: str
    size_bytes: int


class FrozenExternalFileHash(BaseModel):
    path: str
    sha256: str
    size_bytes: int


class FrozenExternalInput(BaseModel):
    source_id: str
    product: str
    original_path: str
    dataset_version: str
    observed_at: str
    freshness_status: str
    semantic_status: str
    files: list[FrozenExternalFileHash] = Field(default_factory=list)


class ExperimentEvidenceManifest(BaseModel):
    experiment_id: str
    output_dir: str
    commit_sha: str
    seed_hash: str
    runtime_settings_hash: str
    metric_definition_hash: str
    files: list[FrozenFileHash] = Field(default_factory=list)
    external_inputs: list[FrozenExternalInput] = Field(default_factory=list)
