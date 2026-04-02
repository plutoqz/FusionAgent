from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from utils.local_smoke import build_run_request_from_case, run_local_v2_smoke, validate_smoke_result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local GeoFusion v2 smoke test against a running API.")
    parser.add_argument(
        "--case-dir",
        default=str(REPO_ROOT / "tests" / "golden_cases" / "building_disaster_flood"),
        help="Path to a golden case directory.",
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL.")
    parser.add_argument("--timeout", type=float, default=180.0, help="Smoke timeout in seconds.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    case_dir = Path(args.case_dir).resolve()
    payload = build_run_request_from_case(case_dir)
    result = run_local_v2_smoke(case_dir, base_url=args.base_url, timeout_sec=args.timeout)
    validate_smoke_result(
        result,
        expected_plan_checks=payload.get("expected_plan_checks"),
        artifact_checks=payload.get("artifact_checks"),
    )

    print(f"run_id={result['run_id']}")
    print(f"phase={result['status']['phase']}")
    print(f"artifact_size={result['artifact_size']}")
    print("artifact_entries=" + ",".join(result.get("artifact_entries", [])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
