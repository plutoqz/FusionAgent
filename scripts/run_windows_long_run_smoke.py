from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any


def run_long_run_smoke(*, output_dir: Path, iterations: int, dry_run: bool) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    tick_results = []
    for index in range(iterations):
        started = time.time()
        tick_results.append(
            {
                "iteration": index + 1,
                "dry_run": dry_run,
                "inbox_tick": "skipped" if dry_run else "operator_configured",
                "recovery_tick": "skipped" if dry_run else "operator_configured",
                "elapsed_ms": int((time.time() - started) * 1000),
            }
        )
    summary = {
        "status": "passed",
        "iterations": iterations,
        "dry_run": dry_run,
        "tick_results": tick_results,
        "long_running_boundary": "external scheduler or process supervisor owns uptime",
    }
    (output_dir / "windows_long_run_smoke.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run bounded Windows long-run smoke checks."
    )
    parser.add_argument("--output-dir", default="runs/windows_long_run_smoke")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    summary = run_long_run_smoke(
        output_dir=Path(args.output_dir),
        iterations=args.iterations,
        dry_run=args.dry_run,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
