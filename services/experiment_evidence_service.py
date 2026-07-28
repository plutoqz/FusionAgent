from __future__ import annotations

import hashlib
from pathlib import Path

from schemas.experiment_evidence import ExperimentEvidenceManifest, FrozenExternalInput, FrozenFileHash


def build_experiment_manifest(
    *,
    experiment_id: str,
    output_dir: Path,
    commit_sha: str,
    seed_hash: str,
    runtime_settings_hash: str,
    metric_definition_hash: str,
    external_inputs: list[dict[str, object]] | None = None,
) -> ExperimentEvidenceManifest:
    output_dir = Path(output_dir)
    files = [
        FrozenFileHash(
            relative_path=str(path.relative_to(output_dir)).replace("\\", "/"),
            sha256=_sha256_file(path),
            size_bytes=path.stat().st_size,
        )
        for path in sorted(output_dir.rglob("*"))
        if path.is_file()
    ]
    return ExperimentEvidenceManifest(
        experiment_id=experiment_id,
        output_dir=str(output_dir),
        commit_sha=commit_sha,
        seed_hash=seed_hash,
        runtime_settings_hash=runtime_settings_hash,
        metric_definition_hash=metric_definition_hash,
        files=files,
        external_inputs=[FrozenExternalInput.model_validate(item) for item in (external_inputs or [])],
    )


def verify_experiment_manifest(manifest: ExperimentEvidenceManifest) -> list[str]:
    output_dir = Path(manifest.output_dir)
    failures: list[str] = []
    for item in manifest.files:
        path = output_dir / item.relative_path
        if not path.exists():
            failures.append(f"{item.relative_path}: missing")
            continue
        current_hash = _sha256_file(path)
        if current_hash != item.sha256:
            failures.append(f"{item.relative_path}: hash changed")
        if path.stat().st_size != item.size_bytes:
            failures.append(f"{item.relative_path}: size changed")
    for source in manifest.external_inputs:
        for item in source.files:
            path = Path(item.path)
            label = f"{source.source_id}:{item.path}"
            if not path.exists():
                failures.append(f"{label}: missing")
                continue
            if _sha256_file(path) != item.sha256:
                failures.append(f"{label}: hash changed")
            if path.stat().st_size != item.size_bytes:
                failures.append(f"{label}: size changed")
    return failures


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
