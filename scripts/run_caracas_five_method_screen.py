"""Serial, narrow typed-road screen; not a confirmatory emergency benchmark."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists():
        raise ValueError("Use a fresh comparison directory")
    root.mkdir(parents=True)
    repo = Path(__file__).resolve().parents[1]
    rows = []
    for method in ("fixed", "rules", "kg", "llm_only", "live"):
        out = root / method
        with (root / f"{method}.log").open("w", encoding="utf-8") as log:
            completed = subprocess.run([
                sys.executable, str(repo / "scripts/run_caracas_closed_loop_smoke.py"),
                "--planner", method, "--output", str(out),
            ], cwd=repo, stdout=log, stderr=subprocess.STDOUT, check=False)
        summary_path = out / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else {}
        attempts = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((out / "provider-calls").glob("*attempt.json"))
        ]
        quality_path = out / "runs" / str(summary.get("run_id")) / "output/quality_report.json"
        quality = json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.exists() else {}
        rows.append({
            "method": method, "exit_code": completed.returncode,
            "phase": summary.get("phase", "no_summary"), "error": summary.get("error"),
            "seconds": summary.get("elapsed_seconds"), "calls": summary.get("planning_call_count", 0),
            "tokens": sum((a.get("usage") or {}).get("total_tokens", 0) for a in attempts if a),
            "quality_accepted": quality.get("accepted"),
            "features": quality.get("metrics", {}).get("feature_count"),
            "dangle_per_100km": quality.get("metrics", {}).get("dangle_endpoint_rate_per_100km"),
            "published": summary.get("artifact") is not None,
            "run_id": summary.get("run_id"),
        })
        (root / "comparison.json").write_text(json.dumps({
            "scope": "exploratory typed-road normal cached-source screen",
            "formal_baselines": False, "independent_repetitions": False,
            "rows": rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(rows[-1], ensure_ascii=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
