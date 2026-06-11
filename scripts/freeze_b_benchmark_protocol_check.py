from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from schemas.benchmark import BenchmarkManifest, DataTier, IndependenceLabel


def check_freeze_b_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest = BenchmarkManifest.model_validate_json(Path(manifest_path).read_text(encoding="utf-8"))
    synthetic_violations = [
        case.case_id
        for case in manifest.cases
        if case.data_tier == DataTier.synthetic
        and case.claim_use == "quality_claim"
        and case.independence_label != IndependenceLabel.algorithm_independent_synthetic
    ]
    task_coverage = sorted({case.task_kind.value for case in manifest.cases})
    report = {
        "ok": not synthetic_violations,
        "manifest_id": manifest.manifest_id,
        "case_count": manifest.case_count,
        "task_coverage": task_coverage,
        "synthetic_quality_claim_violations": synthetic_violations,
    }
    return report


def _output_report(report: dict[str, Any]) -> dict[str, Any]:
    output = dict(report)
    output["synthetic_claim_violations"] = output.pop("synthetic_quality_claim_violations", [])
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check Freeze B benchmark manifest.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-json", default="")
    args = parser.parse_args(argv)
    report = check_freeze_b_manifest(Path(args.manifest))
    output_report = _output_report(report)
    text = json.dumps(output_report, ensure_ascii=False, indent=2)
    print(text)
    if args.output_json:
        Path(args.output_json).write_text(text, encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
