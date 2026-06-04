from __future__ import annotations

import hashlib
import json
from pathlib import Path

from schemas.evidence_lifecycle import EvidenceArtifactRef, EvidenceBundleManifest


RUN_SOURCE_OF_TRUTH = ["request.json", "run.json", "plan.json", "validation.json", "audit.jsonl"]
SCENARIO_SOURCE_OF_TRUTH = [
    "request.json",
    "scenario_summary.json",
    "evaluation.json",
    "kg_path_trace.json",
    "workflow_trace.json",
    "source_coverage.json",
    "failed_children.json",
]


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


def build_scenario_evidence_manifest(scenario_dir: Path) -> EvidenceBundleManifest:
    scenario_dir = Path(scenario_dir)
    summary = _load_json(scenario_dir / "scenario_summary.json")
    child_runs = summary.get("child_runs") if isinstance(summary, dict) else []
    related_run_ids: list[str] = []
    if isinstance(child_runs, list):
        for child in child_runs:
            if not isinstance(child, dict):
                continue
            run_id = str(child.get("run_id") or "").strip()
            if run_id and run_id not in related_run_ids:
                related_run_ids.append(run_id)

    artifacts = [
        _ref(scenario_dir, "request", "request.json", required=False, retention_class="durable_evidence"),
        _ref(scenario_dir, "scenario_summary", "scenario_summary.json", retention_class="durable_evidence"),
        _ref(scenario_dir, "evaluation", "evaluation.json", retention_class="durable_evidence"),
        _ref(scenario_dir, "kg_path_trace", "kg_path_trace.json", retention_class="durable_evidence"),
        _ref(scenario_dir, "workflow_trace", "workflow_trace.json", retention_class="durable_evidence"),
        _ref(scenario_dir, "source_coverage", "source_coverage.json", retention_class="durable_evidence"),
        _ref(scenario_dir, "failed_children", "failed_children.json", required=False, retention_class="durable_evidence"),
    ]
    final_outputs = summary.get("final_outputs") if isinstance(summary, dict) else []
    if isinstance(final_outputs, list):
        for raw_path in final_outputs:
            path = Path(str(raw_path))
            artifacts.append(
                EvidenceArtifactRef(
                    role="child_output",
                    path=str(path),
                    required=False,
                    exists=path.exists(),
                    retention_class="external_reference",
                    content_sha256=_sha256(path) if path.is_file() else None,
                )
            )

    scenario_id = str(summary.get("scenario_id") or scenario_dir.name) if isinstance(summary, dict) else scenario_dir.name
    return EvidenceBundleManifest(
        bundle_id=scenario_id,
        bundle_kind="scenario",
        source_of_truth=[name for name in SCENARIO_SOURCE_OF_TRUTH if (scenario_dir / name).exists()],
        artifacts=artifacts,
        related_run_ids=related_run_ids,
        related_scenario_ids=[scenario_id],
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


def _load_json(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
