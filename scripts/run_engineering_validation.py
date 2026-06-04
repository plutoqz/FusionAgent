from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", default="docs/superpowers/validation/engineering_validation_matrix.yaml")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    payload = json.loads(Path(args.matrix).read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    for case in cases:
        print(f"{case['case_id']}: {case['scenario_name']} [{case['aoi_class']}]")
    if args.dry_run:
        return 0
    raise SystemExit("Non-dry-run execution is implemented in the next validation runner slice.")


if __name__ == "__main__":
    raise SystemExit(main())
