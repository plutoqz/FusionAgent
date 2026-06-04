from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from schemas.engineering_validation import EngineeringValidationCase


def load_matrix_cases(matrix_path: Path, selected_case_ids: list[str] | None = None) -> list[EngineeringValidationCase]:
    payload = json.loads(Path(matrix_path).read_text(encoding="utf-8"))
    raw_cases = payload.get("cases", [])
    selected = set(selected_case_ids or [])
    cases = [EngineeringValidationCase.model_validate(case) for case in raw_cases if isinstance(case, dict)]
    if selected:
        cases = [case for case in cases if case.case_id in selected]
    return cases


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", default="docs/superpowers/validation/engineering_validation_matrix.yaml")
    parser.add_argument("--case", action="append", default=[], help="Case id to run. Can be passed multiple times.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    cases = load_matrix_cases(Path(args.matrix), selected_case_ids=args.case)
    for case in cases:
        print(f"{case.case_id}: {case.scenario_name} [{case.aoi_class}]")
    if args.dry_run:
        return 0
    raise SystemExit("Non-dry-run execution is implemented in the next validation runner slice.")


if __name__ == "__main__":
    raise SystemExit(main())
