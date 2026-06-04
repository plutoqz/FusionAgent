from __future__ import annotations

import hashlib
from pathlib import Path

from schemas.evidence_lifecycle import EvidenceArtifactRef, EvidenceBundleManifest


RUN_SOURCE_OF_TRUTH = ["request.json", "run.json", "plan.json", "validation.json", "audit.jsonl"]


def build_run_evidence_manifest(run_dir: Path) -> EvidenceBundleManifest:
    run_dir = Path(run_dir)
    artifacts = [
        _ref(run_dir, "request", "request.json", required=False, retention_class="durable_evidence"),
        _ref(run_dir, "run_status", "run.json", retention_class="durable_evidence"),
        _ref(run_dir, "plan", "plan.json", retention_class="durable_evidence"),
        _ref(run_dir, "validation", "validation.json", retention_class="durable_evidence"),
        _ref(run_dir, "audit", "audit.jsonl", retention_class="durable_evidence"),
        _ref(run_dir, "quality_report", "output/quality_report.json", required=False, retention_class="durable_evidence"),
    ]
    artifacts.extend(_canonical_outputs(run_dir))
    return EvidenceBundleManifest(
        bundle_id=run_dir.name,
        bundle_kind="run",
        source_of_truth=[name for name in RUN_SOURCE_OF_TRUTH if (run_dir / name).exists()],
        artifacts=artifacts,
        related_run_ids=[run_dir.name],
    )


def _canonical_outputs(run_dir: Path) -> list[EvidenceArtifactRef]:
    output_dir = run_dir / "output"
    if not output_dir.exists():
        return []
    paths = sorted(output_dir.glob("*_fusion_result.zip")) + sorted(output_dir.glob("*.gpkg"))
    return [
        EvidenceArtifactRef(
            role="canonical_output",
            path=str(path),
            required=True,
            exists=path.exists(),
            retention_class="durable_evidence",
            content_sha256=_sha256(path) if path.is_file() else None,
        )
        for path in paths
    ]


def _ref(
    root: Path,
    role: str,
    relative_path: str,
    *,
    required: bool = True,
    retention_class: str = "transient",
) -> EvidenceArtifactRef:
    path = root / relative_path
    return EvidenceArtifactRef(
        role=role,
        path=str(path),
        required=required,
        exists=path.exists(),
        retention_class=retention_class,
        content_sha256=_sha256(path) if path.is_file() else None,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
