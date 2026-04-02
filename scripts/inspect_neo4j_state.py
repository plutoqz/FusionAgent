from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.bootstrap import MANAGED_LABEL, inspect_graph_state, resolve_graph_target
from utils.local_runtime import apply_local_dependency_defaults


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect Neo4j state for FusionAgent without mutating data.")
    parser.add_argument(
        "--managed-only",
        action="store_true",
        help="Only inspect FusionAgent-managed nodes and relationships.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    apply_local_dependency_defaults(required=True)

    import os

    uri = os.environ["GEOFUSION_NEO4J_URI"]
    user = os.environ["GEOFUSION_NEO4J_USER"]
    password = os.environ["GEOFUSION_NEO4J_PASSWORD"]
    database = os.environ.get("GEOFUSION_NEO4J_DATABASE") or None

    resolved = resolve_graph_target(uri=uri, user=user, password=password, database=database)
    inventory = inspect_graph_state(
        uri=uri,
        user=user,
        password=password,
        database=resolved["database_used"],
        managed_only=args.managed_only,
    )
    report = {
        **resolved,
        "managed_label": MANAGED_LABEL,
        "inventory": inventory,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
