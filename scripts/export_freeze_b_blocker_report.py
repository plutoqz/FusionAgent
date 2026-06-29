from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from schemas.benchmark import BenchmarkManifest


DEFAULT_SOURCE_ROOT_CANDIDATES: tuple[str, ...] = (
    r"E:\fyx\data\Benin",
    r"D:\fyx\data\Benin",
)


def _artifact_status(case: Any) -> dict[str, Any]:
    raw_path = case.model_extra.get("precomputed_artifact_path") if case.model_extra else None
    artifact_path = Path(str(raw_path)) if raw_path else None
    exists = bool(artifact_path and artifact_path.exists() and artifact_path.is_file())
    if exists or case.claim_use == "smoke_only":
        reason = None
    elif artifact_path is None:
        reason = "missing_precomputed_artifact_path"
    else:
        reason = "precomputed_artifact_not_found"
    return {
        "case_id": case.case_id,
        "task_kind": case.task_kind.value,
        "claim_use": case.claim_use,
        "data_tier": case.data_tier.value,
        "precomputed_artifact_path": str(artifact_path).replace("\\", "/") if artifact_path else None,
        "artifact_exists": exists,
        "ready": exists or case.claim_use == "smoke_only",
        "blocking_reason": reason,
    }


def build_blocker_report(
    manifest_path: Path,
    *,
    source_roots: list[Path],
    output_json: Path,
    output_markdown: Path | None = None,
) -> dict[str, Any]:
    manifest = BenchmarkManifest.model_validate_json(Path(manifest_path).read_text(encoding="utf-8"))
    root_checks = [
        {
            "path": str(root).replace("\\", "/"),
            "exists": root.exists(),
            "is_dir": root.is_dir(),
        }
        for root in source_roots
    ]
    cases = [_artifact_status(case) for case in manifest.cases]
    blocking_cases = [case for case in cases if not case["ready"]]
    real_or_robustness_blocking = [
        case
        for case in blocking_cases
        if case["claim_use"] in {"quality_claim", "robustness_claim"}
    ]
    payload = {
        "source": "freeze-b-local-blocker-report",
        "scope": (
            "Local readiness blocker report for the original Freeze B benchmark. "
            "This records missing local source roots and missing precomputed artifacts; "
            "it is not a benchmark result."
        ),
        "manifest_id": manifest.manifest_id,
        "manifest_path": str(Path(manifest_path)).replace("\\", "/"),
        "source_root_checks": root_checks,
        "source_root_available": any(item["exists"] and item["is_dir"] for item in root_checks),
        "case_count": len(cases),
        "blocking_case_count": len(blocking_cases),
        "real_or_robustness_blocking_case_count": len(real_or_robustness_blocking),
        "ready": not blocking_cases,
        "blocker_summary": _blocker_summary(root_checks, real_or_robustness_blocking),
        "cases": cases,
    }
    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if output_markdown is not None:
        output_markdown = Path(output_markdown)
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        output_markdown.write_text(_render_markdown(payload), encoding="utf-8")
    return payload


def _blocker_summary(root_checks: list[dict[str, Any]], blocking_cases: list[dict[str, Any]]) -> str:
    source_available = any(item["exists"] and item["is_dir"] for item in root_checks)
    reasons = sorted({str(case["blocking_reason"]) for case in blocking_cases if case.get("blocking_reason")})
    if not blocking_cases:
        return "No original Freeze B benchmark blocker detected."
    if not source_available:
        return (
            "Original Freeze B is blocked locally because the Benin source root is unavailable "
            f"and non-smoke cases remain blocked by: {', '.join(reasons)}."
        )
    return f"Original Freeze B is blocked by non-smoke cases with: {', '.join(reasons)}."


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Freeze B Local Blocker Report",
        "",
        payload["scope"],
        "",
        f"- Manifest: `{payload['manifest_path']}`",
        f"- Ready: {payload['ready']}",
        f"- Source root available: {payload['source_root_available']}",
        f"- Blocking non-smoke cases: {payload['real_or_robustness_blocking_case_count']}",
        f"- Summary: {payload['blocker_summary']}",
        "",
        "## Source Roots",
        "",
        "| Path | Exists | Directory |",
        "| --- | --- | --- |",
    ]
    for item in payload["source_root_checks"]:
        lines.append("| {path} | {exists} | {is_dir} |".format(**item))
    lines.extend(
        [
            "",
            "## Cases",
            "",
            "| Case | Task | Claim Use | Data Tier | Ready | Blocking Reason | Artifact |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for case in payload["cases"]:
        lines.append(
            "| {case_id} | {task_kind} | {claim_use} | {data_tier} | {ready} | {blocking_reason} | `{artifact}` |".format(
                artifact=case["precomputed_artifact_path"] or "",
                **case,
            )
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export local blocker report for original Freeze B benchmark.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--source-root", action="append", default=[])
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", default="")
    args = parser.parse_args(argv)
    source_roots = [Path(item) for item in (args.source_root or DEFAULT_SOURCE_ROOT_CANDIDATES)]
    payload = build_blocker_report(
        Path(args.manifest),
        source_roots=source_roots,
        output_json=Path(args.output_json),
        output_markdown=Path(args.output_markdown) if args.output_markdown else None,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
