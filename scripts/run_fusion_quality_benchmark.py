from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from schemas.benchmark import BenchmarkCaseResult, BenchmarkManifest
from services.artifact_evaluation_service import evaluate_vector_artifact
from services.fusion_quality_benchmark_service import compare_metrics_to_thresholds, summarize_benchmark_results


def run_manifest(manifest_path: Path, *, output_dir: Path) -> dict[str, Any]:
    manifest = BenchmarkManifest.model_validate_json(Path(manifest_path).read_text(encoding="utf-8"))
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[BenchmarkCaseResult] = []
    for case in manifest.cases:
        artifact_path = Path(str(case.model_extra.get("precomputed_artifact_path") if case.model_extra else ""))
        if not artifact_path.exists():
            raise FileNotFoundError(f"Benchmark case {case.case_id} has no precomputed artifact at {artifact_path}")
        source_artifact_paths = _source_artifact_paths(case.model_extra or {})
        metrics = evaluate_vector_artifact(
            artifact_path,
            required_fields=["geometry"],
            source_artifact_paths=source_artifact_paths,
        )
        threshold_results = compare_metrics_to_thresholds(metrics, case.metrics)
        accepted = case.claim_use != "smoke_only" and bool(threshold_results) and all(threshold_results.values())
        results.append(
            BenchmarkCaseResult(
                case_id=case.case_id,
                task_kind=case.task_kind,
                baseline_id=case.baselines[0].baseline_id if case.baselines else "smoke",
                artifact_path=str(artifact_path),
                metrics=metrics,
                threshold_results=threshold_results,
                accepted_for_claim=accepted,
                feature_alignment_summary=_feature_alignment_summary(metrics),
            )
        )
    summary = summarize_benchmark_results(manifest, results).model_dump(mode="json")
    (output_dir / "benchmark_results.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "benchmark_summary.md").write_text(_render_markdown(summary), encoding="utf-8")
    return summary


def _source_artifact_paths(extra: dict[str, Any]) -> dict[str, Path]:
    raw = extra.get("source_artifact_paths")
    if not isinstance(raw, dict):
        return {}
    return {str(source_id): Path(str(path)) for source_id, path in raw.items() if str(path)}


def _feature_alignment_summary(metrics: dict[str, Any]) -> dict[str, Any]:
    alignment = metrics.get("feature_alignment")
    if not isinstance(alignment, dict):
        return {"status": "not_available", "reason": "feature_alignment_missing"}
    keys = [
        "status",
        "reason",
        "source_feature_count",
        "fused_feature_count",
        "matched_source_count",
        "matched_fused_count",
        "unmatched_source_count",
        "unmatched_fused_count",
        "match_recall",
        "match_precision_proxy",
        "attribute_agreement",
        "geometry_deviation_p95_m",
    ]
    return {key: alignment.get(key) for key in keys if key in alignment}


def _render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Fusion Quality Benchmark Summary",
        "",
        f"- Manifest: `{summary['manifest_id']}`",
        f"- Results: {summary['result_count']}",
        f"- Quality claim cases: {summary['quality_claim_case_count']}",
        f"- Accepted quality claim cases: {summary['accepted_quality_claim_count']}",
        "",
        "| Case | Task | Baseline | Accepted | Alignment recall | Alignment precision |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in summary["results"]:
        alignment = result.get("feature_alignment_summary") or {}
        lines.append(
            f"| {result['case_id']} | {result['task_kind']} | {result['baseline_id']} | "
            f"{result['accepted_for_claim']} | {_fmt_metric(alignment.get('match_recall'))} | "
            f"{_fmt_metric(alignment.get('match_precision_proxy'))} |"
        )
    lines.append("")
    return "\n".join(lines)


def _fmt_metric(value: Any) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run FusionAgent quality benchmark manifest.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run_manifest(Path(args.manifest), output_dir=Path(args.output_dir)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
