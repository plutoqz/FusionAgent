from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from fusion_algorithms.contracts import PoiFusionParams, WaterPolygonFusionParams, params_from_mapping
from fusion_algorithms.poi_fusion import run_poi_geohash_priority_fusion
from fusion_algorithms.road_conflation_v7 import RoadConflationV7Config, run_road_conflation_v7
from fusion_algorithms.water_fusion import fuse_water_polygons
from fusion_algorithms.waterways_conflation_v7 import WaterwaysConflationV7Config, run_waterways_conflation_v7
from services.runtime_source_aliases import (
    LINE_SOURCE_ALIASES,
    POI_SOURCE_ALIASES,
    POI_SOURCE_PRIORITY_ORDER,
    POLYGON_WATER_SOURCE_ALIASES,
    alias_paths,
)
from services.tile_partition_service import TileSpec


def _read(path: Path, target_crs: str) -> gpd.GeoDataFrame:
    frame = gpd.read_file(path)
    if frame.empty:
        return gpd.GeoDataFrame(frame, geometry="geometry", crs=target_crs)
    return frame.set_crs(target_crs) if frame.crs is None else frame.to_crs(target_crs)


def _write(frame: gpd.GeoDataFrame, output_dir: Path, name: str, target_crs: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output = frame.copy()
    if output.crs is None:
        output = output.set_crs(target_crs)
    else:
        output = output.to_crs(target_crs)
    path = output_dir / f"{name}.gpkg"
    output.to_file(path, driver="GPKG")
    return path


def _empty_output(output_dir: Path, name: str, target_crs: str, columns: dict[str, str] | None = None) -> Path:
    data: dict[str, pd.Series] = {}
    for column, dtype in (columns or {"source_id": "object"}).items():
        data[column] = pd.Series(dtype=dtype)
    frame = gpd.GeoDataFrame(
        data,
        geometry=gpd.GeoSeries([], dtype="geometry", crs=target_crs),
        crs=target_crs,
    )
    return _write(frame, output_dir, name, target_crs)


def _config_from_mapping(config_cls, values: dict[str, Any] | None, *, target_crs: str | None = None):
    allowed = {item.name for item in fields(config_cls)}
    config_values = {key: value for key, value in dict(values or {}).items() if key in allowed}
    if target_crs is not None and "target_crs" in allowed:
        config_values["target_crs"] = target_crs
    return config_cls(**config_values)


def _line_source_paths(sources: dict[str, Path]) -> dict[str, Path]:
    return {**sources, **alias_paths(sources, LINE_SOURCE_ALIASES)}


def _polygon_source_paths(sources: dict[str, Path]) -> dict[str, Path]:
    return {**sources, **alias_paths(sources, POLYGON_WATER_SOURCE_ALIASES)}


def _poi_source_paths(sources: dict[str, Path]) -> dict[str, Path]:
    return {**sources, **alias_paths(sources, POI_SOURCE_ALIASES)}


def run_road_tile(
    tile: TileSpec,
    sources: dict[str, Path],
    output_dir: Path,
    target_crs: str,
    parameters: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    del tile
    paths = _line_source_paths(sources)
    base_path = paths.get("raw.osm.road") or paths.get("OSM")
    supplement_path = paths.get("raw.overture.transportation") or paths.get("raw.overture.road") or paths.get("OVERTURE")
    if base_path is None or supplement_path is None:
        return _empty_output(output_dir, "road_fused", target_crs), {
            "algorithm_id": "algo.fusion.road.conflation.v7",
            "warning": "missing road source",
        }
    base = _read(base_path, target_crs)
    supplement = _read(supplement_path, target_crs)
    if base.empty and supplement.empty:
        return _empty_output(output_dir, "road_fused", target_crs), {
            "algorithm_id": "algo.fusion.road.conflation.v7",
            "stats": {"final_count": 0},
        }
    config = _config_from_mapping(RoadConflationV7Config, parameters, target_crs=target_crs)
    result = run_road_conflation_v7(base, supplement, config=config)
    return _write(result.frame, output_dir, "road_fused", target_crs), {
        "algorithm_id": result.lineage.get("algorithm_id", "algo.fusion.road.conflation.v7"),
        "stats": result.stats,
        "config": result.config,
        "warnings": result.warnings,
    }


def run_water_polygon_tile(
    tile: TileSpec,
    sources: dict[str, Path],
    output_dir: Path,
    target_crs: str,
    parameters: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    del tile
    paths = _polygon_source_paths(sources)
    base_path = paths.get("raw.osm.water") or paths.get("OSM")
    supplement_path = paths.get("raw.hydrolakes.water") or paths.get("raw.local.water") or paths.get("HYDROLAKES") or paths.get("LOCAL_WATER")
    if base_path is None or supplement_path is None:
        return _empty_output(output_dir, "water_polygon_fused", target_crs, {"source_id": "object", "feature_kind": "object"}), {
            "algorithm_id": "algo.fusion.water_polygon.priority_merge.v2",
            "warning": "missing water polygon source",
        }
    base = _read(base_path, target_crs)
    supplement = _read(supplement_path, target_crs)
    params = params_from_mapping(WaterPolygonFusionParams, parameters)
    fused = fuse_water_polygons(base, supplement, params)
    if fused.empty:
        fused = gpd.GeoDataFrame(
            {"feature_kind": pd.Series(dtype="object")},
            geometry=gpd.GeoSeries([], dtype="geometry", crs=target_crs),
            crs=target_crs,
        )
    else:
        fused = fused.set_crs(target_crs) if fused.crs is None else fused.to_crs(target_crs)
        fused["feature_kind"] = "polygon"
    return _write(fused, output_dir, "water_polygon_fused", target_crs), {
        "algorithm_id": "algo.fusion.water_polygon.priority_merge.v2",
        "stats": {"final_count": int(len(fused))},
    }


def run_waterways_tile(
    tile: TileSpec,
    sources: dict[str, Path],
    output_dir: Path,
    target_crs: str,
    parameters: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    del tile
    paths = _line_source_paths(sources)
    base_path = paths.get("raw.osm.waterways") or paths.get("OSM")
    supplement_path = (
        paths.get("raw.hydrorivers.water")
        or paths.get("raw.local.pakistan.waterways")
        or paths.get("HYDRORIVERS")
        or paths.get("LOCAL_WATERWAYS")
    )
    if base_path is None or supplement_path is None:
        return _empty_output(output_dir, "waterways_fused", target_crs, {"source_id": "object", "feature_kind": "object"}), {
            "algorithm_id": "algo.fusion.waterways.conflation.v7",
            "warning": "missing waterways source",
        }
    base = _read(base_path, target_crs)
    supplement = _read(supplement_path, target_crs)
    if base.empty and supplement.empty:
        return _empty_output(output_dir, "waterways_fused", target_crs, {"source_id": "object", "feature_kind": "object"}), {
            "algorithm_id": "algo.fusion.waterways.conflation.v7",
            "stats": {"final_count": 0},
        }
    config = _config_from_mapping(WaterwaysConflationV7Config, parameters, target_crs=target_crs)
    result = run_waterways_conflation_v7(base, supplement, config=config)
    frame = result.frame.copy()
    frame["feature_kind"] = "line"
    return _write(frame, output_dir, "waterways_fused", target_crs), {
        "algorithm_id": result.lineage.get("algorithm_id", "algo.fusion.waterways.conflation.v7"),
        "stats": result.stats,
        "config": result.config,
        "warnings": result.warnings,
    }


def run_poi_tile(
    tile: TileSpec,
    sources: dict[str, Path],
    output_dir: Path,
    target_crs: str,
    parameters: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    del tile
    paths = _poi_source_paths(sources)
    ordered_sources: dict[str, gpd.GeoDataFrame] = {}
    for alias in POI_SOURCE_PRIORITY_ORDER:
        path = paths.get(alias)
        if path is None:
            continue
        frame = _read(path, target_crs)
        if not frame.empty:
            ordered_sources[alias] = frame
    if not ordered_sources:
        return _empty_output(
            output_dir,
            "poi_fused",
            target_crs,
            {"source_id": "object", "source_rank": "int64", "MATCHED": "bool"},
        ), {
            "algorithm_id": "algo.fusion.poi.geohash_neighbor_match.v1",
            "stats": {"final_count": 0},
        }
    params = params_from_mapping(
        PoiFusionParams,
        {
            "source_priority_order": tuple(ordered_sources.keys()),
            **parameters,
        },
    )
    fused = run_poi_geohash_priority_fusion(ordered_sources, params)
    rank_by_source = {name: rank for rank, name in enumerate(params.source_priority_order, start=1)}
    if "SRC" in fused.columns:
        source_from_src = fused["SRC"].replace({"base": params.source_priority_order[0]})
        if len(params.source_priority_order) > 1:
            source_from_src = source_from_src.replace({"target": params.source_priority_order[-1]})
        fused["source_rank"] = source_from_src.map(rank_by_source).fillna(99).astype(int)
    else:
        fused["source_rank"] = 99
    if "MATCHED" not in fused.columns:
        fused["MATCHED"] = False
    return _write(fused, output_dir, "poi_fused", target_crs), {
        "algorithm_id": "algo.fusion.poi.geohash_neighbor_match.v1",
        "stats": {"final_count": int(len(fused)), "source_count": len(ordered_sources)},
        "source_priority_order": list(params.source_priority_order),
    }
