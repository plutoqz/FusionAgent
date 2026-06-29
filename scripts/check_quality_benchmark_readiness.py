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


def check_readiness(manifest_path: Path, *, output_json: Path, output_markdown: Path | None = None) -> dict[str, Any]:
    manifest = BenchmarkManifest.model_validate_json(Path(manifest_path).read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = []
    for case in manifest.cases:
        raw_path = case.model_extra.get("precomputed_artifact_path") if case.model_extra else None
        artifact_path = Path(str(raw_path)) if raw_path else None
        exists = bool(artifact_path and artifact_path.exists() and artifact_path.is_file())
        cases.append(
            {
                "case_id": case.case_id,
                "task_kind": case.task_kind.value,
                "claim_use": case.claim_use,
                "precomputed_artifact_path": str(artifact_path).replace("\\", "/") if artifact_path else None,
                "artifact_exists": exists,
                "ready": exists or case.claim_use == "smoke_only",
                "blocking_reason": None
                if exists or case.claim_use == "smoke_only"
                else "missing_precomputed_artifact_path"
                if artifact_path is None
                else "precomputed_artifact_not_found",
            }
        )
    blocking_cases = [case for case in cases if not case["ready"]]
    payload = {
        "manifest_id": manifest.manifest_id,
        "manifest_path": str(Path(manifest_path)).replace("\\", "/"),
        "case_count": len(cases),
        "ready_case_count": len(cases) - len(blocking_cases),
        "blocking_case_count": len(blocking_cases),
        "ready": not blocking_cases,
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


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Fusion Quality Benchmark Readiness",
        "",
        f"- Manifest: `{payload['manifest_path']}`",
        f"- Ready: {payload['ready']}",
        f"- Cases: {payload['case_count']}",
        f"- Blocking cases: {payload['blocking_case_count']}",
        "",
        "| Case | Task | Claim Use | Artifact | Ready | Blocking Reason |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case in payload["cases"]:
        artifact = case["precomputed_artifact_path"] or ""
        reason = case["blocking_reason"] or ""
        lines.append(
            f"| {case['case_id']} | {case['task_kind']} | {case['claim_use']} | `{artifact}` | {case['ready']} | {reason} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Fusion Quality Benchmark readiness.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", default="")
    args = parser.parse_args(argv)
    payload = check_readiness(
        Path(args.manifest),
        output_json=Path(args.output_json),
        output_markdown=Path(args.output_markdown) if args.output_markdown else None,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 2


if __name__ == "__main__":
    sys.exit(main())
