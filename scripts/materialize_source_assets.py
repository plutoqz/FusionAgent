from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.source_asset_service import SourceAssetService


def _parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if not raw:
        return None
    parts = [item.strip() for item in raw.split(",")]
    if len(parts) != 4:
        raise ValueError("--bbox must be formatted as minx,miny,maxx,maxy")
    minx, miny, maxx, maxy = (float(item) for item in parts)
    if maxx < minx or maxy < miny:
        raise ValueError("--bbox values must satisfy maxx>=minx and maxy>=miny")
    return (minx, miny, maxx, maxy)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prefetch or resolve benchmark source assets into the local cache.")
    parser.add_argument("--source", action="append", required=True, help="Raw source id to materialize.")
    parser.add_argument(
        "--bbox",
        default="",
        help="Optional bbox override for clipped source materialization, formatted as minx,miny,maxx,maxy.",
    )
    parser.add_argument(
        "--cache-dir",
        default=str(REPO_ROOT / "runs" / "source-assets"),
        help="Cache directory for downloaded or extracted source assets.",
    )
    parser.add_argument(
        "--prefer-remote",
        action="store_true",
        help="Ignore existing repo-local Data files and force remote/cache-backed materialization where supported.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    bbox = _parse_bbox(args.bbox)
    service = SourceAssetService(
        repo_root=REPO_ROOT,
        cache_dir=Path(args.cache_dir),
        prefer_local_data=not args.prefer_remote,
    )

    results = []
    for source_id in args.source:
        resolution = service.resolve_raw_source_path(source_id, request_bbox=bbox)
        results.append(
            {
                "source_id": source_id,
                "path": str(resolution.path),
                "source_mode": resolution.source_mode,
                "cache_hit": resolution.cache_hit,
                "version_token": resolution.version_token,
            }
        )

    print(json.dumps({"bbox": bbox, "results": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
