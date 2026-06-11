from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.track_b_national_scale_service import (
    DEFAULT_THEME_SOURCE_IDS,
    TrackBNationalScaleService,
)
from services.aoi_resolution_service import ResolvedAOI


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
    parser.add_argument("--country-name", default="", help="Optional country hint for sources that need country-scoped remote discovery.")
    parser.add_argument("--country-code", default="", help="Optional country code hint paired with --country-name.")
    parser.add_argument("--cache-dir", default=str(REPO_ROOT / "runs" / "track_b_national_scale_cache"))
    parser.add_argument("--google-open-buildings-url", action="append", default=[])
    parser.add_argument("--google-poi-authorization", default="")
    parser.add_argument("--google-places-api-key-env", default="GOOGLE_PLACES_API_KEY")
    parser.add_argument("--google-places-cache-key", default="")
    parser.add_argument("--require-full-autonomous-closure", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    google_poi_authorization_path = Path(args.google_poi_authorization).resolve() if args.google_poi_authorization else None
    google_places_api_key = os.environ.get(args.google_places_api_key_env, "") if args.google_places_api_key_env else ""
    service = TrackBNationalScaleService(
        root_dir=REPO_ROOT,
        cache_dir=Path(args.cache_dir).resolve(),
        google_open_buildings_urls=args.google_open_buildings_url,
        google_poi_authorization_path=google_poi_authorization_path,
        google_places_api_key=google_places_api_key,
        google_places_cache_key=args.google_places_cache_key or None,
    )
    output_root = Path(args.output_root).resolve()
    resolved_aoi = None
    if args.country_name or args.country_code:
        resolved_aoi = ResolvedAOI(
            query=args.country_name or args.country_code or args.job_type,
            display_name=args.country_name or args.country_code or args.job_type,
            country_name=args.country_name or None,
            country_code=args.country_code or None,
            bbox=_parse_bbox(args.bbox),
            confidence=1.0,
            selection_reason="explicit_country_hint",
            candidates=(),
        )
    summary = service.build_theme_evidence(
        job_type=args.job_type,
        source_id=(args.source_id or DEFAULT_THEME_SOURCE_IDS[args.job_type]),
        request_bbox=_parse_bbox(args.bbox),
        target_crs=args.target_crs,
        output_root=output_root,
        tile_width_m=args.tile_width_m,
        tile_height_m=args.tile_height_m,
        overlap_m=args.overlap_m,
        resolved_aoi=resolved_aoi,
    )
    print(f"claim_state={summary['claim_state']}")
    print(f"tile_count={summary['tile_count']}")
    print(f"artifact_path={summary['artifact_path']}")
    if args.require_full_autonomous_closure:
        inspection_summary_path = output_root / "inspection_summary.json"
        try:
            inspection_summary = json.loads(inspection_summary_path.read_text(encoding="utf-8"))
            readiness = inspection_summary.get("autonomous_readiness") or {}
            status = readiness.get("status")
            missing_source_ids = list(readiness.get("missing_required_source_ids") or [])
        except Exception as exc:  # noqa: BLE001
            status = "inspection_summary_unreadable"
            missing_source_ids = []
            print(f"full_autonomous_closure_required status={status} error={type(exc).__name__}: {exc}")
            return 2
        if status != "full_autonomous_closure":
            missing_text = ",".join(str(source_id) for source_id in missing_source_ids) or "<none-recorded>"
            print(f"full_autonomous_closure_required status={status} missing_required_source_ids={missing_text}")
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
