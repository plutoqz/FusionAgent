from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import Field

from benchmark_platform.canonical import canonical_json_bytes, canonical_sha256
from benchmark_platform.models import (
    BenchmarkPlatformValidationError,
    FailureClass,
    FailureRecord,
    StrictRuntimeModel,
)


RUN_STAGES = (
    "created",
    "design_bound",
    "templates_validated",
    "generated",
    "relations_validated",
    "views_projected",
    "audited",
    "development_complete",
)
RunStage = Literal[
    "created",
    "design_bound",
    "templates_validated",
    "generated",
    "relations_validated",
    "views_projected",
    "audited",
    "development_complete",
]

_RESERVED_JSON_ARTIFACTS = {
    "run_manifest.json",
    "design_binding.json",
    "validation_report.json",
    "leakage_audit.json",
}
_JSONL_ARTIFACTS = {
    "generation_attempts.jsonl",
    "instances.jsonl",
    "planner_packets.jsonl",
    "evaluator_packets.jsonl",
    "human_blind_packets.jsonl",
}
_STORE_MANAGED_ARTIFACTS = {"checkpoint.json", "checksums.json"}


class StoreFailureCode(str, Enum):
    OUTPUT_EXISTS = "store.output_exists"
    RESUME_HASH_DRIFT = "store.resume_hash_drift"
    ILLEGAL_STAGE = "store.illegal_stage"
    PARTIAL_PUBLISH = "store.partial_publish"


class StoreError(BenchmarkPlatformValidationError):
    pass


class RunBinding(StrictRuntimeModel):
    run_id: str = Field(pattern=r"^BDV1-DEV-[A-Z0-9-]+$")
    design_id: str = Field(min_length=1)
    design_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    template_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    seed_namespace: str = Field(min_length=1)
    master_seed: int = Field(ge=0)
    code_revision: str = Field(min_length=1)
    input_hashes: dict[str, str] = Field(min_length=1)


class StageCheckpoint(StrictRuntimeModel):
    stage: RunStage
    input_hashes: dict[str, str]
    output_hashes: dict[str, str]


class RunCheckpoint(StrictRuntimeModel):
    checkpoint_contract_id: Literal["fusionagent.benchmark-platform.store-checkpoint.v1"]
    binding: RunBinding
    stage: RunStage
    terminal_status: Literal["nonterminal", "development_complete", "failed_retained"]
    completed_stages: tuple[StageCheckpoint, ...]


class ResumeRequest(StrictRuntimeModel):
    run_root: str = Field(min_length=1)
    expected_stage: RunStage
    binding: RunBinding


class ResumeState(StrictRuntimeModel):
    run_root: str
    stage: RunStage
    checkpoint_sha256: str


class TerminalBinding(StrictRuntimeModel):
    run_id: str
    checksums_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    covered_file_count: int = Field(ge=1)


def _fail(code: StoreFailureCode, message: str, path: tuple[str | int, ...] = ()) -> None:
    raise StoreError(
        [
            FailureRecord(
                failure_class=FailureClass.RUNTIME_INVALID_STATE,
                message=message,
                path=path,
                details={"code": code.value},
            )
        ]
    )


def _sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _file_sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _atomic_write(path: Path, data: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _validate_relative_path(relative_path: str) -> PurePosixPath:
    path = PurePosixPath(relative_path)
    if path.is_absolute() or ".." in path.parts or path.name in _STORE_MANAGED_ARTIFACTS:
        _fail(StoreFailureCode.PARTIAL_PUBLISH, "artifact path is not publishable", (relative_path,))
    if str(path) in _RESERVED_JSON_ARTIFACTS or (
        len(path.parts) == 2 and path.parts[0] == "template_snapshots" and path.suffix == ".json"
    ):
        return path
    _fail(StoreFailureCode.PARTIAL_PUBLISH, "artifact path is outside the declared run layout", (relative_path,))


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        _fail(StoreFailureCode.RESUME_HASH_DRIFT, f"cannot read retained artifact: {error}", (path.name,))
    if not isinstance(value, dict):
        _fail(StoreFailureCode.RESUME_HASH_DRIFT, "expected JSON object", (path.name,))
    return value


def _load_checkpoint(root: Path) -> RunCheckpoint:
    try:
        return RunCheckpoint.model_validate(_load_json(root / "checkpoint.json"))
    except Exception as error:
        if isinstance(error, StoreError):
            raise
        _fail(StoreFailureCode.RESUME_HASH_DRIFT, f"checkpoint is invalid: {error}", ("checkpoint.json",))


def _write_checkpoint(root: Path, checkpoint: RunCheckpoint) -> None:
    _atomic_write(root / "checkpoint.json", canonical_json_bytes(checkpoint))


def _all_published_files(root: Path, *, include_checksums: bool = False) -> list[Path]:
    files = [path for path in root.rglob("*") if path.is_file()]
    return sorted(
        [path for path in files if include_checksums or path.name != "checksums.json"],
        key=lambda path: path.relative_to(root).as_posix(),
    )


class ArtifactStore:
    """Offline, write-new storage for one development run root."""

    def __init__(self, root: Path) -> None:
        self.root = root

    @classmethod
    def create_new(cls, root: str | Path, binding: RunBinding) -> "ArtifactStore":
        final_root = Path(root)
        if final_root.exists():
            _fail(StoreFailureCode.OUTPUT_EXISTS, "run root already exists", (str(final_root),))
        final_root.parent.mkdir(parents=True, exist_ok=True)
        staging_root = final_root.parent / f".{final_root.name}.staging-{uuid.uuid4().hex}"
        try:
            staging_root.mkdir()
            (staging_root / "template_snapshots").mkdir()
            _atomic_write(
                staging_root / "run_manifest.json",
                canonical_json_bytes({"run_id": binding.run_id, "partition": "development", "binding": binding}),
            )
            _atomic_write(staging_root / "design_binding.json", canonical_json_bytes(binding))
            for filename in _JSONL_ARTIFACTS:
                _atomic_write(staging_root / filename, b"")
            checkpoint = RunCheckpoint(
                checkpoint_contract_id="fusionagent.benchmark-platform.store-checkpoint.v1",
                binding=binding,
                stage="created",
                terminal_status="nonterminal",
                completed_stages=(),
            )
            _write_checkpoint(staging_root, checkpoint)
            if final_root.exists():
                _fail(StoreFailureCode.OUTPUT_EXISTS, "run root already exists", (str(final_root),))
            os.rename(staging_root, final_root)
        except StoreError:
            if staging_root.exists():
                shutil.rmtree(staging_root)
            raise
        except OSError as error:
            if staging_root.exists():
                shutil.rmtree(staging_root)
            _fail(StoreFailureCode.PARTIAL_PUBLISH, f"atomic run-root publish failed: {error}", (str(final_root),))
        return cls(final_root)

    def write_json_artifact(self, relative_path: str, value: Mapping[str, Any]) -> str:
        path = _validate_relative_path(relative_path)
        target = self.root.joinpath(*path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(target, canonical_json_bytes(dict(value)))
        return _file_sha256(target)

    def append_jsonl(self, relative_path: str, value: Mapping[str, Any]) -> str:
        if relative_path not in _JSONL_ARTIFACTS:
            _fail(StoreFailureCode.PARTIAL_PUBLISH, "artifact is not a declared JSONL stream", (relative_path,))
        target = self.root / relative_path
        existing = target.read_bytes() if target.exists() else b""
        _atomic_write(target, existing + canonical_json_bytes(dict(value)) + b"\n")
        return _file_sha256(target)

    def append_instance(self, value: Mapping[str, Any]) -> str:
        instance_id = value.get("instance_id")
        instance_sha256 = value.get("instance_sha256")
        if not isinstance(instance_id, str) or not isinstance(instance_sha256, str):
            _fail(StoreFailureCode.PARTIAL_PUBLISH, "instance identity is required", ("instances.jsonl",))
        target = self.root / "instances.jsonl"
        for line in target.read_text(encoding="utf-8").splitlines():
            existing = json.loads(line)
            if existing.get("instance_id") == instance_id or existing.get("instance_sha256") == instance_sha256:
                _fail(StoreFailureCode.OUTPUT_EXISTS, "duplicate valid instance is forbidden", ("instances.jsonl", instance_id))
        return self.append_jsonl("instances.jsonl", value)

    def commit_stage(
        self,
        stage: RunStage,
        *,
        input_hashes: Mapping[str, str],
        output_paths: Sequence[str],
    ) -> RunCheckpoint:
        checkpoint = _load_checkpoint(self.root)
        if checkpoint.terminal_status != "nonterminal":
            _fail(StoreFailureCode.ILLEGAL_STAGE, "terminal run cannot accept a new stage", (stage,))
        current_index = RUN_STAGES.index(checkpoint.stage)
        expected = RUN_STAGES[current_index + 1] if current_index + 1 < len(RUN_STAGES) else None
        if stage != expected:
            _fail(StoreFailureCode.ILLEGAL_STAGE, f"expected stage {expected}, received {stage}", (stage,))
        normalized_outputs: dict[str, str] = {}
        for relative_path in sorted(set(output_paths)):
            path = _validate_relative_path(relative_path) if relative_path not in _JSONL_ARTIFACTS else PurePosixPath(relative_path)
            target = self.root.joinpath(*path.parts)
            if not target.is_file():
                _fail(StoreFailureCode.PARTIAL_PUBLISH, "declared stage output is missing", (relative_path,))
            normalized_outputs[relative_path] = _file_sha256(target)
        record = StageCheckpoint(stage=stage, input_hashes=dict(sorted(input_hashes.items())), output_hashes=normalized_outputs)
        terminal_status: Literal["nonterminal", "development_complete", "failed_retained"] = (
            "development_complete" if stage == "development_complete" else "nonterminal"
        )
        updated = checkpoint.model_copy(
            update={
                "stage": stage,
                "terminal_status": terminal_status,
                "completed_stages": (*checkpoint.completed_stages, record),
            }
        )
        _write_checkpoint(self.root, updated)
        return updated

    def resume(self, request: ResumeRequest) -> ResumeState:
        if Path(request.run_root) != self.root:
            _fail(StoreFailureCode.RESUME_HASH_DRIFT, "resume root does not match store root", ("run_root",))
        checkpoint = _load_checkpoint(self.root)
        if checkpoint.binding != request.binding or checkpoint.stage != request.expected_stage:
            _fail(StoreFailureCode.RESUME_HASH_DRIFT, "resume binding or checkpoint stage drifted", ("checkpoint.json",))
        for stage in checkpoint.completed_stages:
            for relative_path, expected_hash in stage.output_hashes.items():
                target = self.root / relative_path
                if not target.is_file() or _file_sha256(target) != expected_hash:
                    _fail(StoreFailureCode.RESUME_HASH_DRIFT, "retained stage output hash drifted", (relative_path,))
        return ResumeState(
            run_root=str(self.root),
            stage=checkpoint.stage,
            checkpoint_sha256=_file_sha256(self.root / "checkpoint.json"),
        )

    def finalize(self) -> TerminalBinding:
        checkpoint = _load_checkpoint(self.root)
        if checkpoint.stage != "development_complete" or checkpoint.terminal_status != "development_complete":
            _fail(StoreFailureCode.ILLEGAL_STAGE, "only a completed development run can be finalized", (checkpoint.stage,))
        if (self.root / "checksums.json").exists():
            _fail(StoreFailureCode.OUTPUT_EXISTS, "checksums already published", ("checksums.json",))
        files = _all_published_files(self.root)
        checksums = {path.relative_to(self.root).as_posix(): _file_sha256(path) for path in files}
        _atomic_write(self.root / "checksums.json", canonical_json_bytes({"algorithm": "sha256", "files": checksums}))
        return TerminalBinding(
            run_id=checkpoint.binding.run_id,
            checksums_sha256=_file_sha256(self.root / "checksums.json"),
            covered_file_count=len(checksums),
        )

    def verify_terminal(self, binding: TerminalBinding) -> bool:
        checkpoint = _load_checkpoint(self.root)
        if checkpoint.binding.run_id != binding.run_id or not (self.root / "checksums.json").is_file():
            return False
        if _file_sha256(self.root / "checksums.json") != binding.checksums_sha256:
            return False
        checksum_document = _load_json(self.root / "checksums.json")
        files = checksum_document.get("files")
        if not isinstance(files, dict) or len(files) != binding.covered_file_count:
            return False
        return all(
            isinstance(expected, str) and (self.root / relative).is_file() and _file_sha256(self.root / relative) == expected
            for relative, expected in files.items()
        )
