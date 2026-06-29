from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio

try:
    from shapely import make_valid as _shapely_make_valid
except Exception:  # noqa: BLE001
    _shapely_make_valid = None

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fusion_algorithms.contracts import PoiFusionParams
from fusion_algorithms.poi_fusion import run_poi_geohash_priority_fusion
from fusion_algorithms.road_conflation_v7 import RoadConflationV7Config, run_road_conflation_v7
from fusion_algorithms.waterways_conflation_v7 import (
    WaterwaysConflationV7Config,
    run_waterways_conflation_v7,
)


MANIFEST_ID = "freeze-b-caracas-real-v1"
TARGET_CRS = "EPSG:32619"
WGS84 = "EPSG:4326"
BUILDING_OVERLAP_THRESHOLD = 0.10
MIN_BUILDING_AREA_SQ_M = 1.0


def materialize_caracas_real_quality_artifacts(
    *,
    source_root: Path,
    output_dir: Path,
    manifest_path: Path,
    target_crs: str = TARGET_CRS,
) -> dict[str, Any]:
    source_root = Path(source_root)
    output_dir = Path(output_dir)
    manifest_path = Path(manifest_path)
    artifact_dir = output_dir / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    sources = _caracas_sources(source_root)
    _require_sources(sources)

    started = time.perf_counter()
    lineage: list[dict[str, Any]] = []
    cases = [
        _building_case(sources, artifact_dir, lineage, target_crs=target_crs),
        _road_case(sources, artifact_dir, lineage, target_crs=target_crs),
        _waterways_case(sources, artifact_dir, lineage, target_crs=target_crs),
        _water_polygon_case(sources, artifact_dir, lineage, target_crs=target_crs),
        _poi_case(sources, artifact_dir, lineage, target_crs=target_crs),
    ]
    manifest = {
        "manifest_id": MANIFEST_ID,
        "freeze_line": "Freeze B",
        "notes": [
            "Real-data Caracas supplement for Freeze B quality evidence.",
            "Does not replace the original Benin Freeze B benchmark; it records a separate Venezuela/Caracas real-data test.",
            "Building output uses an auditable overlap-priority fixed adapter because the external FusionCode V8 runtime is not bundled in this checkout.",
            "Road, waterways, and POI outputs use checked-in FusionAgent fusion modules.",
            "Water polygon output is a single-source OSM structural-quality sanity case, not a multi-source fusion superiority claim.",
        ],
        "cases": cases,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "source": "caracas-real-quality-materialization",
        "scope": (
            "Materializes real Caracas artifacts and a Freeze B-compatible benchmark manifest. "
            "This is a real-data supplement, not the original Benin benchmark."
        ),
        "manifest_id": MANIFEST_ID,
        "source_root": _display_path(source_root),
        "output_dir": _display_path(output_dir),
        "manifest_path": _display_path(manifest_path),
        "target_crs": target_crs,
        "elapsed_sec": time.perf_counter() - started,
        "source_metadata": {name: _vector_metadata(path) for name, path in sources.items()},
        "artifact_count": len(lineage),
        "artifacts": lineage,
    }
    (output_dir / "materialization_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    (output_dir / "materialization_summary.md").write_text(_render_materialization_markdown(summary), encoding="utf-8")
    return {"manifest": manifest, "summary": summary}


def _caracas_sources(source_root: Path) -> dict[str, Path]:
    return {
        "ms_buildings": source_root / "Microsoft_capital_district.gpkg",
        "google_buildings": source_root / "googlebuildingv3.gpkg",
        "osm_buildings": source_root / "osm" / "buildings.shp",
        "ms_roads": source_root / "microsoft_roads_capital.gpkg",
        "osm_roads": source_root / "osm" / "roads.shp",
        "hydrorivers": source_root / "hydrorivers_capital.gpkg",
        "osm_waterways": source_root / "osm" / "waterways.shp",
        "osm_water": source_root / "osm" / "water.shp",
        "geonames": source_root / "geonames_capital.gpkg",
        "osm_poi": source_root / "osm" / "poi.shp",
    }


def _require_sources(sources: dict[str, Path]) -> None:
    missing = [f"{name}: {path}" for name, path in sources.items() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing Caracas source files: " + "; ".join(missing))


def _building_case(
    sources: dict[str, Path],
    artifact_dir: Path,
    lineage: list[dict[str, Any]],
    *,
    target_crs: str,
) -> dict[str, Any]:
    ms = _prepare_building_source(
        sources["ms_buildings"],
        source_name="MS",
        source_id="raw.microsoft.building",
        priority=1,
        target_crs=target_crs,
    )
    google = _prepare_building_source(
        sources["google_buildings"],
        source_name="GOOGLE",
        source_id="raw.google.open_buildings.vector",
        priority=2,
        target_crs=target_crs,
    )
    osm = _prepare_building_source(
        sources["osm_buildings"],
        source_name="OSM",
        source_id="raw.osm.building",
        priority=3,
        target_crs=target_crs,
    )
    round_1, round_1_stats = _append_unmatched_by_overlap(
        ms,
        google,
        target_label="GOOGLE",
        overlap_threshold=BUILDING_OVERLAP_THRESHOLD,
    )
    fused, round_2_stats = _append_unmatched_by_overlap(
        round_1,
        osm,
        target_label="OSM",
        overlap_threshold=BUILDING_OVERLAP_THRESHOLD,
    )
    fused["fusion_algorithm"] = "overlap_priority_fixed_adapter"
    fused = _to_wgs84(fused)
    artifact = _write_gpkg(fused, artifact_dir / "building_caracas_overlap_priority.gpkg")
    lineage.append(
        {
            "case_id": "case.building.real.caracas",
            "task_kind": "building",
            "artifact_path": _display_path(artifact),
            "algorithm": "overlap_priority_fixed_adapter",
            "algorithm_boundary": "weak baseline/fixed adapter; not external FusionCode V8",
            "input_feature_counts": {
                "MS": len(ms),
                "GOOGLE": len(google),
                "OSM": len(osm),
            },
            "output_feature_count": len(fused),
            "stats": {
                "round_1_ms_google": round_1_stats,
                "round_2_fused_osm": round_2_stats,
                "overlap_threshold": BUILDING_OVERLAP_THRESHOLD,
                "min_building_area_sq_m": MIN_BUILDING_AREA_SQ_M,
            },
        }
    )
    return {
        "case_id": "case.building.real.caracas",
        "task_kind": "building",
        "data_tier": "real",
        "independence_label": "real_source",
        "claim_use": "quality_claim",
        "aoi": {"name": "venezuela-caracas-capital", "bbox": [-67.17, 10.38, -66.86, 10.57]},
        "sources": [
            {"source_id": "raw.microsoft.building", "version_token": "caracas-local-2026-06-25"},
            {"source_id": "raw.google.open_buildings.vector", "version_token": "caracas-local-2026-06-25"},
            {"source_id": "raw.osm.building", "version_token": "caracas-local-2026-06-25"},
        ],
        "baselines": [
            {
                "baseline_id": "fixed_adapter_overlap_priority",
                "runner": "adapter_direct",
                "description": "Priority-ordered overlap deduplication baseline: MS > Google > OSM.",
            }
        ],
        "metrics": [
            {"metric_name": "feature_count", "operator": "gt", "threshold": 0},
            {"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0},
            {"metric_name": "duplicate_geometry_rate", "operator": "lte", "threshold": 0.25},
        ],
        "expected_artifact_roles": ["fused_vector"],
        "evidence_boundary": "real multi-source weak baseline; not a statistical superiority claim",
        "precomputed_artifact_path": _display_path(artifact),
    }


def _road_case(
    sources: dict[str, Path],
    artifact_dir: Path,
    lineage: list[dict[str, Any]],
    *,
    target_crs: str,
) -> dict[str, Any]:
    config = RoadConflationV7Config(
        target_crs=target_crs,
        output_crs=WGS84,
        profile="balanced",
        log_every_n=5000,
    )
    result = run_road_conflation_v7(sources["osm_roads"], sources["ms_roads"], config=config)
    frame = result.frame.copy()
    frame["source_id"] = frame.get("source_layer", pd.Series("", index=frame.index)).map(
        {
            "base": "raw.osm.road",
            "supplement": "raw.microsoft.road",
        }
    ).fillna("raw.road.unknown")
    frame["fusion_algorithm"] = "road_conflation_v7"
    artifact = _write_gpkg(_to_wgs84(frame), artifact_dir / "road_caracas_conflation_v7.gpkg")
    lineage.append(
        {
            "case_id": "case.road.real.caracas",
            "task_kind": "road",
            "artifact_path": _display_path(artifact),
            "algorithm": "run_road_conflation_v7",
            "input_feature_counts": {
                "OSM": _feature_count(sources["osm_roads"]),
                "MS": _feature_count(sources["ms_roads"]),
            },
            "output_feature_count": len(frame),
            "config": asdict(config),
            "stats": result.stats,
            "warnings": result.warnings,
        }
    )
    return {
        "case_id": "case.road.real.caracas",
        "task_kind": "road",
        "data_tier": "real",
        "independence_label": "real_source",
        "claim_use": "quality_claim",
        "aoi": {"name": "venezuela-caracas-capital", "bbox": [-67.17, 10.38, -66.86, 10.57]},
        "sources": [
            {"source_id": "raw.osm.road", "version_token": "caracas-local-2026-06-25"},
            {"source_id": "raw.microsoft.road", "version_token": "caracas-local-2026-06-25"},
        ],
        "baselines": [{"baseline_id": "fusionagent_road_v7", "runner": "adapter_direct"}],
        "metrics": [
            {"metric_name": "feature_count", "operator": "gt", "threshold": 0},
            {"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0},
            {"metric_name": "zero_length_geometry_count", "operator": "eq", "threshold": 0},
        ],
        "expected_artifact_roles": ["fused_vector"],
        "precomputed_artifact_path": _display_path(artifact),
    }


def _waterways_case(
    sources: dict[str, Path],
    artifact_dir: Path,
    lineage: list[dict[str, Any]],
    *,
    target_crs: str,
) -> dict[str, Any]:
    config = WaterwaysConflationV7Config(
        target_crs=target_crs,
        output_crs=WGS84,
        log_every_n=1000,
    )
    result = run_waterways_conflation_v7(sources["osm_waterways"], sources["hydrorivers"], config=config)
    frame = result.frame.copy()
    frame["source_id"] = frame.get("source_layer", pd.Series("", index=frame.index)).map(
        {
            "base": "raw.osm.waterways",
            "supplement": "raw.hydrorivers.waterways",
        }
    ).fillna("raw.waterways.unknown")
    frame["fusion_algorithm"] = "waterways_conflation_v7"
    artifact = _write_gpkg(_to_wgs84(frame), artifact_dir / "waterways_caracas_conflation_v7.gpkg")
    lineage.append(
        {
            "case_id": "case.waterways.real.caracas",
            "task_kind": "waterways",
            "artifact_path": _display_path(artifact),
            "algorithm": "run_waterways_conflation_v7",
            "input_feature_counts": {
                "OSM": _feature_count(sources["osm_waterways"]),
                "HydroRIVERS": _feature_count(sources["hydrorivers"]),
            },
            "output_feature_count": len(frame),
            "config": asdict(config),
            "stats": result.stats,
            "warnings": result.warnings,
        }
    )
    return {
        "case_id": "case.waterways.real.caracas",
        "task_kind": "waterways",
        "data_tier": "real",
        "independence_label": "real_source",
        "claim_use": "quality_claim",
        "aoi": {"name": "venezuela-caracas-capital", "bbox": [-67.17, 10.38, -66.86, 10.57]},
        "sources": [
            {"source_id": "raw.osm.waterways", "version_token": "caracas-local-2026-06-25"},
            {"source_id": "raw.hydrorivers.waterways", "version_token": "caracas-local-2026-06-25"},
        ],
        "baselines": [{"baseline_id": "fusionagent_waterways_v7", "runner": "adapter_direct"}],
        "metrics": [
            {"metric_name": "feature_count", "operator": "gt", "threshold": 0},
            {"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0},
            {"metric_name": "zero_length_geometry_count", "operator": "eq", "threshold": 0},
        ],
        "expected_artifact_roles": ["fused_vector"],
        "precomputed_artifact_path": _display_path(artifact),
    }


def _water_polygon_case(
    sources: dict[str, Path],
    artifact_dir: Path,
    lineage: list[dict[str, Any]],
    *,
    target_crs: str,
) -> dict[str, Any]:
    frame = _load_vector(sources["osm_water"], target_crs=target_crs, geometry_types={"Polygon", "MultiPolygon"})
    frame = _minimal_frame(
        frame,
        source_id="raw.osm.water_polygon",
        source_name="OSM",
        fusion_algorithm="single_source_passthrough",
    )
    artifact = _write_gpkg(_to_wgs84(frame), artifact_dir / "water_polygon_caracas_osm_passthrough.gpkg")
    lineage.append(
        {
            "case_id": "case.water_polygon.real.caracas.single_source_sanity",
            "task_kind": "water_polygon",
            "artifact_path": _display_path(artifact),
            "algorithm": "single_source_passthrough",
            "algorithm_boundary": "single-source structural sanity only",
            "input_feature_counts": {"OSM": _feature_count(sources["osm_water"])},
            "output_feature_count": len(frame),
        }
    )
    return {
        "case_id": "case.water_polygon.real.caracas.single_source_sanity",
        "task_kind": "water_polygon",
        "data_tier": "real",
        "independence_label": "real_source",
        "claim_use": "quality_claim",
        "aoi": {"name": "venezuela-caracas-capital", "bbox": [-67.17, 10.38, -66.86, 10.57]},
        "sources": [{"source_id": "raw.osm.water_polygon", "version_token": "caracas-local-2026-06-25"}],
        "baselines": [
            {
                "baseline_id": "fixed_adapter_single_source_passthrough",
                "runner": "adapter_direct",
                "description": "Single-source OSM water polygon structural-quality sanity case.",
            }
        ],
        "metrics": [
            {"metric_name": "feature_count", "operator": "gt", "threshold": 0},
            {"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0},
        ],
        "expected_artifact_roles": ["fused_vector"],
        "evidence_boundary": "single-source sanity case; not multi-source fusion evidence",
        "precomputed_artifact_path": _display_path(artifact),
    }


def _poi_case(
    sources: dict[str, Path],
    artifact_dir: Path,
    lineage: list[dict[str, Any]],
    *,
    target_crs: str,
) -> dict[str, Any]:
    geonames = _load_vector(sources["geonames"], target_crs=target_crs, geometry_types={"Point", "MultiPoint"})
    osm = _load_vector(sources["osm_poi"], target_crs=target_crs, geometry_types={"Point", "MultiPoint"})
    geonames = _minimal_frame(geonames, source_id="raw.geonames.poi", source_name="GNG", fusion_algorithm="input")
    osm = _minimal_frame(osm, source_id="raw.osm.poi", source_name="OSM", fusion_algorithm="input")
    fused = run_poi_geohash_priority_fusion(
        {"GNG": geonames, "OSM": osm},
        PoiFusionParams(
            duplicate_distance_m=250.0,
            source_priority_order=("GNG", "OSM"),
        ),
    )
    fused["source_id"] = fused.get("SRC", pd.Series("", index=fused.index)).map(
        {
            "base": "raw.geonames.poi",
            "target": "raw.osm.poi",
        }
    ).fillna(fused.get("source_id", "raw.poi.unknown"))
    fused["fusion_algorithm"] = "poi_geohash_priority_fusion"
    artifact = _write_gpkg(_to_wgs84(fused), artifact_dir / "poi_caracas_geonames_osm.gpkg")
    lineage.append(
        {
            "case_id": "case.poi.real.caracas",
            "task_kind": "poi",
            "artifact_path": _display_path(artifact),
            "algorithm": "run_poi_geohash_priority_fusion",
            "input_feature_counts": {
                "GeoNames": len(geonames),
                "OSM": len(osm),
            },
            "output_feature_count": len(fused),
            "params": {
                "duplicate_distance_m": 250.0,
                "source_priority_order": ["GNG", "OSM"],
            },
        }
    )
    return {
        "case_id": "case.poi.real.caracas",
        "task_kind": "poi",
        "data_tier": "real",
        "independence_label": "real_source",
        "claim_use": "quality_claim",
        "aoi": {"name": "venezuela-caracas-capital", "bbox": [-67.17, 10.38, -66.86, 10.57]},
        "sources": [
            {"source_id": "raw.geonames.poi", "version_token": "caracas-local-2026-06-25"},
            {"source_id": "raw.osm.poi", "version_token": "caracas-local-2026-06-25"},
        ],
        "baselines": [{"baseline_id": "fusionagent_poi_neighbor_match", "runner": "adapter_direct"}],
        "metrics": [
            {"metric_name": "feature_count", "operator": "gt", "threshold": 0},
            {"metric_name": "invalid_geometry_rate", "operator": "eq", "threshold": 0.0},
            {"metric_name": "duplicate_geometry_rate", "operator": "lte", "threshold": 0.25},
        ],
        "expected_artifact_roles": ["fused_vector"],
        "precomputed_artifact_path": _display_path(artifact),
    }


def _prepare_building_source(
    path: Path,
    *,
    source_name: str,
    source_id: str,
    priority: int,
    target_crs: str,
) -> gpd.GeoDataFrame:
    frame = _load_vector(path, target_crs=target_crs, geometry_types={"Polygon", "MultiPolygon"})
    frame = frame.explode(index_parts=False).reset_index(drop=True)
    frame = frame[frame.geometry.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    frame["area_m2"] = frame.geometry.area
    frame = frame[frame["area_m2"] >= MIN_BUILDING_AREA_SQ_M].copy()
    result = gpd.GeoDataFrame(
        {
            "source_id": [source_id] * len(frame),
            "source_name": [source_name] * len(frame),
            "source_priority": [priority] * len(frame),
            "source_feature_id": [f"{source_name}:{idx}" for idx in range(len(frame))],
            "matched": [False] * len(frame),
            "matched_source_id": [""] * len(frame),
            "match_score": [0.0] * len(frame),
            "area_m2": frame["area_m2"].astype(float).tolist(),
        },
        geometry=frame.geometry,
        crs=frame.crs,
    )
    return result.reset_index(drop=True)


def _append_unmatched_by_overlap(
    base: gpd.GeoDataFrame,
    target: gpd.GeoDataFrame,
    *,
    target_label: str,
    overlap_threshold: float,
) -> tuple[gpd.GeoDataFrame, dict[str, Any]]:
    if base.empty:
        return target.copy(), {"target": target_label, "matched_target_count": 0, "unmatched_target_count": len(target)}
    if target.empty:
        return base.copy(), {"target": target_label, "matched_target_count": 0, "unmatched_target_count": 0}

    base_lookup = base[["geometry"]].copy().reset_index(drop=True)
    base_lookup["_base_row"] = np.arange(len(base_lookup))
    target_lookup = target[["geometry"]].copy().reset_index(drop=True)
    target_lookup["_target_row"] = np.arange(len(target_lookup))
    candidates = gpd.sjoin(
        target_lookup[["_target_row", "geometry"]],
        base_lookup[["_base_row", "geometry"]],
        how="inner",
        predicate="intersects",
    )
    matched_target_rows: set[int] = set()
    max_overlap = 0.0
    if not candidates.empty:
        target_rows = candidates["_target_row"].to_numpy(dtype=int)
        base_rows = candidates["_base_row"].to_numpy(dtype=int)
        target_geoms = target.geometry.iloc[target_rows].reset_index(drop=True)
        base_geoms = base.geometry.iloc[base_rows].reset_index(drop=True)
        intersections = target_geoms.intersection(base_geoms).area.to_numpy()
        min_areas = np.minimum(target_geoms.area.to_numpy(), base_geoms.area.to_numpy())
        overlaps = intersections / np.maximum(min_areas, 1e-9)
        max_overlap = float(overlaps.max(initial=0.0))
        matched_target_rows = {int(row) for row in target_rows[overlaps >= overlap_threshold]}

    unmatched = target.iloc[[idx for idx in range(len(target)) if idx not in matched_target_rows]].copy()
    fused = gpd.GeoDataFrame(pd.concat([base, unmatched], ignore_index=True), geometry="geometry", crs=base.crs)
    stats = {
        "target": target_label,
        "base_input_count": int(len(base)),
        "target_input_count": int(len(target)),
        "candidate_pair_count": int(len(candidates)),
        "matched_target_count": int(len(matched_target_rows)),
        "unmatched_target_count": int(len(unmatched)),
        "output_count": int(len(fused)),
        "max_overlap": max_overlap,
    }
    return fused, stats


def _load_vector(path: Path, *, target_crs: str, geometry_types: set[str]) -> gpd.GeoDataFrame:
    frame = gpd.read_file(path)
    if frame.crs is None:
        frame = frame.set_crs(WGS84)
    frame = frame.to_crs(target_crs)
    frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
    frame["geometry"] = _make_valid_geometry(frame.geometry)
    frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
    if geometry_types:
        frame = frame[frame.geometry.geom_type.isin(geometry_types)].copy()
    return frame.reset_index(drop=True)


def _make_valid_geometry(series: gpd.GeoSeries) -> gpd.GeoSeries:
    def _fix(geom):
        if geom is None or geom.is_empty or geom.is_valid:
            return geom
        if _shapely_make_valid is not None:
            return _shapely_make_valid(geom)
        return geom.buffer(0)

    return series.apply(_fix)


def _minimal_frame(
    frame: gpd.GeoDataFrame,
    *,
    source_id: str,
    source_name: str,
    fusion_algorithm: str,
) -> gpd.GeoDataFrame:
    name = frame["name"].fillna("").astype(str) if "name" in frame.columns else pd.Series([""] * len(frame))
    result = gpd.GeoDataFrame(
        {
            "source_id": [source_id] * len(frame),
            "source_name": [source_name] * len(frame),
            "source_feature_id": [f"{source_name}:{idx}" for idx in range(len(frame))],
            "name": name.tolist(),
            "fusion_algorithm": [fusion_algorithm] * len(frame),
        },
        geometry=frame.geometry,
        crs=frame.crs,
    )
    return result.reset_index(drop=True)


def _to_wgs84(frame: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if frame.crs is None:
        return frame.set_crs(WGS84)
    return frame.to_crs(WGS84)


def _write_gpkg(frame: gpd.GeoDataFrame, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = frame.copy()
    clean = clean.drop(columns=[column for column in ["fid", "fid_1", "fid_2"] if column in clean.columns])
    clean = clean.loc[:, ~clean.columns.duplicated()]
    for column in clean.columns:
        if column == clean.geometry.name:
            continue
        if clean[column].dtype == "object":
            clean[column] = clean[column].map(_serialize_cell)
    clean.to_file(path, driver="GPKG")
    return path


def _serialize_cell(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return value


def _feature_count(path: Path) -> int:
    try:
        value = pyogrio.read_info(path).get("features")
        return int(value) if value is not None else 0
    except Exception:  # noqa: BLE001
        return 0


def _vector_metadata(path: Path) -> dict[str, Any]:
    try:
        info = pyogrio.read_info(path)
    except Exception as exc:  # noqa: BLE001
        return {"path": _display_path(path), "readable": False, "error": str(exc)}
    fields = info.get("fields")
    return {
        "path": _display_path(path),
        "readable": True,
        "feature_count": info.get("features"),
        "geometry_type": str(info.get("geometry_type") or ""),
        "crs": str(info.get("crs") or ""),
        "bounds": [float(value) for value in info.get("total_bounds") or []],
        "fields": [str(value) for value in list(fields)[:20]] if fields is not None else [],
    }


def _display_path(path: Path) -> str:
    resolved = Path(path)
    try:
        return str(resolved.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


def _render_materialization_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Caracas Real Quality Materialization",
        "",
        summary["scope"],
        "",
        f"- Manifest: `{summary['manifest_path']}`",
        f"- Source root: `{summary['source_root']}`",
        f"- Output dir: `{summary['output_dir']}`",
        f"- Target CRS: `{summary['target_crs']}`",
        f"- Artifacts: {summary['artifact_count']}",
        "",
        "| Case | Task | Algorithm | Output Features | Artifact | Boundary |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for artifact in summary["artifacts"]:
        lines.append(
            "| {case_id} | {task_kind} | {algorithm} | {output_feature_count} | `{artifact_path}` | {boundary} |".format(
                boundary=artifact.get("algorithm_boundary", ""),
                **artifact,
            )
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize real Caracas quality benchmark artifacts.")
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--target-crs", default=TARGET_CRS)
    args = parser.parse_args(argv)
    result = materialize_caracas_real_quality_artifacts(
        source_root=Path(args.source_root),
        output_dir=Path(args.output_dir),
        manifest_path=Path(args.manifest),
        target_crs=args.target_crs,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
