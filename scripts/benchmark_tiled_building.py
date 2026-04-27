"""
Expected outputs:
- timing.json
- source_profile_snapshot.json
- tile_manifest.json
- benchmark_summary.md
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import geopandas as gpd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.source_profile_service import SourceProfileService
from services.tile_partition_service import TilePartitionService
from services.tiled_building_runtime_service import TiledBuildingRuntimeService
from utils.shp_zip import zip_shapefile_bundle
from utils.vector_clip import clip_frame_to_request_bbox, clip_zip_to_request_bbox


def _parse_bbox(value: str) -> tuple[float, float, float, float]:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("--bbox must contain four comma-separated numbers")
    return (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))


def _load_profile_map(source_root: Path) -> dict[str, dict[str, Any]]:
    payload = SourceProfileService().profile_benin_root(source_root)
    return {item["source_id"]: item for item in payload["profiles"]}


def _materialize_bbox_bundle(*, source_path: Path, request_bbox: tuple[float, float, float, float], output_zip: Path) -> Path:
    frame = gpd.read_file(source_path, bbox=request_bbox)
    clipped = clip_frame_to_request_bbox(frame, request_bbox, request_crs="EPSG:4326")
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    bundle_dir = output_zip.parent / output_zip.stem
    bundle_dir.mkdir(parents=True, exist_ok=True)
    shp_path = bundle_dir / source_path.name
    clipped.to_file(shp_path)
    return zip_shapefile_bundle(shp_path, output_zip)


def _feature_count(path: Path) -> int:
    return int(len(gpd.read_file(path).index))


def _select_reference_profile(profile_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    for source_id in [
        "raw.local.microsoft.building",
        "raw.microsoft.building",
        "raw.google.building",
        "raw.google.open_buildings.vector",
    ]:
        profile = profile_map.get(source_id)
        if profile is not None:
            return profile
    raise KeyError("No building reference profile available for benchmark")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark tiled building runtime preparation for Benin data")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--bbox", required=True, help="minx,miny,maxx,maxy in EPSG:4326")
    parser.add_argument("--target-crs", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--tile-width-m", type=float, default=5000.0)
    parser.add_argument("--tile-height-m", type=float, default=5000.0)
    parser.add_argument("--overlap-m", type=float, default=64.0)
    parser.add_argument("--max-workers", type=int, default=2)
    args = parser.parse_args()

    source_root = Path(args.source_root)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    request_bbox = _parse_bbox(args.bbox)

    timing: dict[str, float] = {}

    started = time.perf_counter()
    profile_map = _load_profile_map(source_root)
    timing["profile"] = time.perf_counter() - started
    (output_root / "source_profile_snapshot.json").write_text(
        json.dumps({"profiles": list(profile_map.values())}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    osm_profile = profile_map["raw.osm.building"]
    ref_profile = _select_reference_profile(profile_map)

    partition_service = TilePartitionService(
        tile_width_m=args.tile_width_m,
        tile_height_m=args.tile_height_m,
        overlap_m=args.overlap_m,
    )
    tile_manifest = partition_service.partition_bbox(
        bbox=request_bbox,
        bbox_crs="EPSG:4326",
        working_crs=args.target_crs,
    )
    (output_root / "tile_manifest.json").write_text(
        json.dumps(tile_manifest.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    clip_started = time.perf_counter()
    bundles_dir = output_root / "bundles"
    osm_aoi_zip = _materialize_bbox_bundle(
        source_path=Path(osm_profile["canonical_path"]),
        request_bbox=request_bbox,
        output_zip=bundles_dir / "osm_aoi.zip",
    )
    ref_aoi_zip = _materialize_bbox_bundle(
        source_path=Path(ref_profile["canonical_path"]),
        request_bbox=request_bbox,
        output_zip=bundles_dir / "ref_aoi.zip",
    )
    preclipped_dir = output_root / "preclipped_tiles"
    preclipped_dir.mkdir(parents=True, exist_ok=True)
    for tile in tile_manifest.tiles:
        tile_dir = preclipped_dir / tile.tile_id
        tile_dir.mkdir(parents=True, exist_ok=True)
        clip_zip_to_request_bbox(osm_aoi_zip, tile_dir / "osm.zip", request_bbox=tile.buffered_bbox)
        clip_zip_to_request_bbox(ref_aoi_zip, tile_dir / "ref.zip", request_bbox=tile.buffered_bbox)
    timing["clip"] = time.perf_counter() - clip_started

    tile_started_at: dict[str, float] = {}
    first_tile_start: float | None = None
    last_tile_complete: float | None = None
    stitch_completed_at: float | None = None

    def on_event(kind: str, details: dict[str, Any]) -> None:
        nonlocal first_tile_start, last_tile_complete, stitch_completed_at
        now = time.perf_counter()
        if kind == "tile_execution_started":
            tile_id = str(details.get("tile_id") or "")
            tile_started_at[tile_id] = now
            if first_tile_start is None:
                first_tile_start = now
        elif kind == "tile_execution_completed":
            last_tile_complete = now
        elif kind == "tile_stitch_completed":
            stitch_completed_at = now

    runtime_service = TiledBuildingRuntimeService(max_workers=args.max_workers)
    fuse_started = time.perf_counter()
    result = runtime_service.run_tiled_building_job(
        run_id="benin-benchmark",
        tile_manifest=tile_manifest,
        osm_bundle_factory=lambda tile, target_path: preclipped_dir / tile.tile_id / "osm.zip",
        ref_bundle_factory=lambda tile, target_path: preclipped_dir / tile.tile_id / "ref.zip",
        output_dir=output_root / "runtime_output",
        target_crs=args.target_crs,
        on_event=on_event,
    )
    total_runtime = time.perf_counter() - fuse_started
    if first_tile_start is None:
        timing["fuse"] = total_runtime
        timing["stitch"] = 0.0
    else:
        tile_end = last_tile_complete or stitch_completed_at or time.perf_counter()
        stitch_end = stitch_completed_at or time.perf_counter()
        timing["fuse"] = max(0.0, tile_end - first_tile_start)
        timing["stitch"] = max(0.0, stitch_end - tile_end)

    final_feature_count = _feature_count(result.output_shp)
    timing_path = output_root / "timing.json"
    timing_path.write_text(
        json.dumps(
            {
                "timings_sec": timing,
                "tile_count": result.tile_count,
                "stitched_feature_count": result.stitched_feature_count,
                "final_feature_count": final_feature_count,
                "selected_profiles": {
                    "osm": osm_profile["source_id"],
                    "reference": ref_profile["source_id"],
                },
                "output_shp": str(result.output_shp),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    summary = "\n".join(
        [
            "# Benin Tiled Building Benchmark",
            "",
            f"- source root: `{source_root}`",
            f"- bbox: `{args.bbox}`",
            f"- target crs: `{args.target_crs}`",
            f"- osm source: `{osm_profile['source_id']}`",
            f"- reference source: `{ref_profile['source_id']}`",
            f"- tile count: `{result.tile_count}`",
            f"- final feature count: `{final_feature_count}`",
            f"- profile sec: `{timing['profile']:.3f}`",
            f"- clip sec: `{timing['clip']:.3f}`",
            f"- fuse sec: `{timing['fuse']:.3f}`",
            f"- stitch sec: `{timing['stitch']:.3f}`",
            "",
            f"- timing json: `{timing_path}`",
            f"- tile manifest: `{output_root / 'tile_manifest.json'}`",
            f"- source profile snapshot: `{output_root / 'source_profile_snapshot.json'}`",
        ]
    )
    (output_root / "benchmark_summary.md").write_text(summary, encoding="utf-8")


if __name__ == "__main__":
    main()
