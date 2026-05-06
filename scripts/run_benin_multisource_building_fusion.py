"""
Run Benin-scale multi-source building fusion with tiled FusionCode primitives.

Expected outputs:
- timing.json
- source_profile_snapshot.json
- tile_manifest.json
- selected_sources.json
- benchmark_summary.md
- runtime_output/fused_buildings.gpkg
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from services.source_profile_service import SourceProfileService
from services.tile_partition_service import TilePartitionService
from services.tiled_building_runtime_service import TiledBuildingRuntimeService


DEFAULT_BENIN_BBOX = (0.75, 6.10, 3.90, 12.50)
DEFAULT_SOURCE_PRIORITY_ORDER = ("MS", "OBM", "GG", "OSM")
VECTOR_PROFILE_TO_SOURCE_NAME = {
    "raw.local.microsoft.building": "MS",
    "raw.openbuildingmap.building": "OBM",
    "raw.google.open_buildings.vector": "GG",
    "raw.osm.building": "OSM",
}
RASTER_PROFILE_TO_NAME = {
    "raw.google.building_presence.raster": "building_presence",
    "raw.google.building_height.raster": "building_height",
}


def _parse_bbox(value: str | None) -> tuple[float, float, float, float]:
    if not value:
        return DEFAULT_BENIN_BBOX
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise ValueError("--bbox must contain four comma-separated numbers")
    return (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))


def _profile_map(payload: dict[str, object]) -> dict[str, dict[str, object]]:
    profiles = payload.get("profiles") or []
    return {str(item["source_id"]): dict(item) for item in profiles if isinstance(item, dict) and item.get("source_id")}


def _path_from_profile(profile: dict[str, object]) -> Path:
    value = str(profile.get("canonical_path") or "").strip()
    if not value:
        raise ValueError(f"Profile has no canonical_path: {profile.get('source_id')}")
    return Path(value)


def _select_benin_vector_sources(profile_map: dict[str, dict[str, object]]) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    for profile_id, source_name in VECTOR_PROFILE_TO_SOURCE_NAME.items():
        profile = profile_map.get(profile_id)
        if profile is None:
            raise KeyError(profile_id)
        sources[source_name] = _path_from_profile(profile)
    return {name: sources[name] for name in DEFAULT_SOURCE_PRIORITY_ORDER}


def _select_benin_rasters(profile_map: dict[str, dict[str, object]]) -> dict[str, Path]:
    rasters: dict[str, Path] = {}
    for profile_id, raster_name in RASTER_PROFILE_TO_NAME.items():
        profile = profile_map.get(profile_id)
        if profile is not None:
            rasters[raster_name] = _path_from_profile(profile)
    return rasters


def _select_benin_context_vectors(road_shp: Path | None) -> dict[str, Path]:
    if road_shp is None:
        return {}
    road_path = Path(road_shp)
    if not road_path.exists():
        raise FileNotFoundError(f"Road shapefile does not exist: {road_path}")
    return {"roads": road_path}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run tiled FusionCode building fusion for Benin national data")
    parser.add_argument("--source-root", required=True, help="Benin source root, e.g. E:\\fyx\\data\\Benin")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--bbox", default=None, help="Optional minx,miny,maxx,maxy in EPSG:4326; defaults to Benin bbox")
    parser.add_argument("--target-crs", default="EPSG:32631")
    parser.add_argument("--tile-width-m", type=float, default=10000.0)
    parser.add_argument("--tile-height-m", type=float, default=10000.0)
    parser.add_argument("--overlap-m", type=float, default=96.0)
    parser.add_argument("--max-workers", type=int, default=4)
    parser.add_argument("--height-output-field", default="height_raster")
    parser.add_argument("--n-jobs", type=int, default=-1)
    parser.add_argument("--road-shp", default=None, help="Optional road shapefile for building-road conflict resolution")
    args = parser.parse_args()

    source_root = Path(args.source_root)
    output_root = Path(args.output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    request_bbox = _parse_bbox(args.bbox)
    timing: dict[str, float] = {}
    events: list[dict[str, Any]] = []

    started = time.perf_counter()
    profile_payload = SourceProfileService().profile_benin_root(source_root)
    profile_map = _profile_map(profile_payload)
    vector_sources = _select_benin_vector_sources(profile_map)
    raster_sources = _select_benin_rasters(profile_map)
    context_vectors = _select_benin_context_vectors(Path(args.road_shp) if args.road_shp else None)
    timing["profile"] = time.perf_counter() - started
    (output_root / "source_profile_snapshot.json").write_text(
        json.dumps(profile_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_root / "selected_sources.json").write_text(
        json.dumps(
            {
                "vector_sources": {key: str(value) for key, value in vector_sources.items()},
                "raster_sources": {key: str(value) for key, value in raster_sources.items()},
                "context_vectors": {key: str(value) for key, value in context_vectors.items()},
                "source_priority_order": list(DEFAULT_SOURCE_PRIORITY_ORDER),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

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

    def on_event(kind: str, details: dict[str, Any]) -> None:
        events.append({"kind": kind, "details": details, "elapsed_sec": time.perf_counter() - fusion_started})

    runtime = TiledBuildingRuntimeService(max_workers=args.max_workers)
    fusion_started = time.perf_counter()
    result = runtime.run_tiled_multisource_building_job(
        run_id="benin-national-multisource",
        tile_manifest=tile_manifest,
        vector_sources=vector_sources,
        raster_sources=raster_sources,
        context_vectors=context_vectors,
        output_dir=output_root / "runtime_output",
        target_crs=args.target_crs,
        source_priority_order=DEFAULT_SOURCE_PRIORITY_ORDER,
        parameters={
            "height_output_field": args.height_output_field,
            "n_jobs": args.n_jobs,
        },
        on_event=on_event,
    )
    timing["fusion"] = time.perf_counter() - fusion_started

    timing_path = output_root / "timing.json"
    timing_path.write_text(
        json.dumps(
            {
                "timings_sec": timing,
                "tile_count": result.tile_count,
                "stitched_feature_count": result.stitched_feature_count,
                "output_path": str(result.output_path),
                "events": events,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_root / "benchmark_summary.md").write_text(
        "\n".join(
            [
                "# Benin National Multi-Source Building Fusion",
                "",
                f"- source root: `{source_root}`",
                f"- bbox: `{','.join(str(value) for value in request_bbox)}`",
                f"- target crs: `{args.target_crs}`",
                f"- tile size m: `{args.tile_width_m} x {args.tile_height_m}`",
                f"- overlap m: `{args.overlap_m}`",
                f"- max workers: `{args.max_workers}`",
                f"- source priority order: `{', '.join(DEFAULT_SOURCE_PRIORITY_ORDER)}`",
                f"- raster inputs: `{', '.join(sorted(raster_sources)) or 'none'}`",
                f"- context vectors: `{', '.join(sorted(context_vectors)) or 'none'}`",
                f"- tile count: `{result.tile_count}`",
                f"- stitched feature count: `{result.stitched_feature_count}`",
                f"- profile sec: `{timing['profile']:.3f}`",
                f"- fusion sec: `{timing['fusion']:.3f}`",
                f"- output: `{result.output_path}`",
                f"- timing json: `{timing_path}`",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
