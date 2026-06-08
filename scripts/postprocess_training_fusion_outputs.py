from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.postprocess_service import COUNTRY_CONFIGS, _json_safe, run_country


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Clean training fusion outputs and export Pakistan-schema SHP files.")
    parser.add_argument("--country", action="append", choices=sorted(COUNTRY_CONFIGS))
    parser.add_argument("--no-overwrite", action="store_true")
    args = parser.parse_args(argv)
    countries = args.country or sorted(COUNTRY_CONFIGS)
    summaries = [run_country(COUNTRY_CONFIGS[key], overwrite=not args.no_overwrite) for key in countries]
    print(json.dumps(_json_safe({"runs": summaries}), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
