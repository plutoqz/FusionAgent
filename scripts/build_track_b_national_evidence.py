from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.track_b_national_scale_service import (
    DEFAULT_THEME_SOURCE_IDS,
    TrackBNationalScaleService,
)


def _parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("--bbox must contain four comma-separated numbers")
    return (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Track B national-scale evidence for building, road, water, or poi.")
    parser.add_argument("--job-type", choices=["building", "road", "water", "poi"], required=True)
    parser.add_argument("--source-id", default="", help="Optional catalog source id override.")
    parser.add_argument("--bbox", required=True, help="minx,miny,maxx,maxy in EPSG:4326")
    parser.add_argument("--target-crs", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--tile-width-m", type=float, default=50_000.0)
    parser.add_argument("--tile-height-m", type=float, default=50_000.0)
    parser.add_argument("--overlap-m", type=float, default=0.0)
    parser.add_argument("--cache-dir", default=str(REPO_ROOT / "runs" / "track_b_national_scale_cache"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    service = TrackBNationalScaleService(
        root_dir=REPO_ROOT,
        cache_dir=Path(args.cache_dir).resolve(),
    )
    summary = service.build_theme_evidence(
        job_type=args.job_type,
        source_id=(args.source_id or DEFAULT_THEME_SOURCE_IDS[args.job_type]),
        request_bbox=_parse_bbox(args.bbox),
        target_crs=args.target_crs,
        output_root=Path(args.output_root).resolve(),
        tile_width_m=args.tile_width_m,
        tile_height_m=args.tile_height_m,
        overlap_m=args.overlap_m,
    )
    print(f"claim_state={summary['claim_state']}")
    print(f"tile_count={summary['tile_count']}")
    print(f"artifact_path={summary['artifact_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
