from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from kg.seed_manifest import build_seed_manifest_payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="kg/seed_manifest.generated.json")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    output = Path(args.output)
    payload = build_seed_manifest_payload()
    if args.check:
        if not output.exists():
            print(f"KG seed manifest is missing: {output}", file=sys.stderr)
            return 1
        checked_in = json.loads(output.read_text(encoding="utf-8"))
        if not manifests_match(checked_in, payload):
            print(f"KG seed manifest is stale: {output}", file=sys.stderr)
            return 1
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return 0


def manifests_match(left: dict, right: dict) -> bool:
    return _stable_payload(left) == _stable_payload(right)


def _stable_payload(payload: dict) -> dict:
    stable = json.loads(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    if isinstance(stable.get("metadata"), dict):
        stable["metadata"]["generated_at"] = ""
    return stable


if __name__ == "__main__":
    raise SystemExit(main())
