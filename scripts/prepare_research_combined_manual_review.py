from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.prepare_research_manual_review import prepare_manual_review_from_roots


def prepare_combined_manual_review(
    *,
    base_root: Path,
    extension_root: Path,
    audit_path: Path,
    output_root: Path,
    packet_seed: int = 20260816,
):
    return prepare_manual_review_from_roots(
        formal_roots=[base_root, extension_root],
        audit_path=audit_path,
        output_root=output_root,
        packet_seed=packet_seed,
        completion_requirement="a complete integrity-valid 90-call combined batch",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare blinded review packets for the combined 90-run batch.")
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--extension-root", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--packet-seed", type=int, default=20260816)
    args = parser.parse_args()
    prepare_combined_manual_review(
        base_root=args.base_root,
        extension_root=args.extension_root,
        audit_path=args.audit,
        output_root=args.output,
        packet_seed=args.packet_seed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
