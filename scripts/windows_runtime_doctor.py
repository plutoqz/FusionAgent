from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.windows_runtime_readiness_service import classify_windows_runtime_readiness


def build_doctor_report(
    repo_root: Path,
    *,
    output_json: Path,
    free_disk_gb: float | None = None,
) -> dict[str, Any]:
    repo_root = Path(repo_root)
    disk = shutil.disk_usage(repo_root)
    effective_free_gb = free_disk_gb if free_disk_gb is not None else disk.free / (1024**3)
    report = classify_windows_runtime_readiness(
        required_paths=[
            repo_root / "scripts" / "start_local.py",
            repo_root / "scripts" / "watch_scenario_inbox.py",
            repo_root / "scripts" / "run_no_ui_maturity_check.py",
        ],
        writable_dirs=[repo_root / "runs", repo_root / "logs"],
        free_disk_gb=effective_free_gb,
    )
    report = {
        **report,
        "repo_root": str(repo_root),
        "known_limits": {
            "cross_platform": "out_of_scope",
            "production_deployment": "out_of_scope",
            "process_supervision": "operator_or_external_scheduler_responsibility",
        },
    }
    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check FusionAgent Windows local runtime readiness."
    )
    parser.add_argument(
        "--output-json",
        default="docs/superpowers/specs/2026-06-10-windows-runtime-doctor.json",
    )
    args = parser.parse_args(argv)
    report = build_doctor_report(REPO_ROOT, output_json=Path(args.output_json))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ready" else 1


if __name__ == "__main__":
    raise SystemExit(main())
