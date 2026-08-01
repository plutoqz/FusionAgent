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
from kg.knowledge_release import KnowledgeReleaseError
from kg.policy_registry import default_policy_registry
from services.large_area_runtime_service import DomainRunner
from services.runtime_source_aliases import (
    LINE_SOURCE_ALIASES,
    POI_SOURCE_ALIASES,
    POI_SOURCE_PRIORITY_ORDER,
    POLYGON_WATER_SOURCE_ALIASES,
    alias_paths,
)
from services.tiled_building_runtime_service import TiledBuildingRuntimeService
from services.tile_partition_service import TileManifest, TileSpec


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
    canonical_sources = dict(sources)
    for source_id, canonical_id in default_policy_registry().source_id_aliases().items():
        if source_id in canonical_sources and canonical_id in canonical_sources:
            canonical_sources.pop(source_id)
    return {**canonical_sources, **alias_paths(canonical_sources, POI_SOURCE_ALIASES)}


def _poi_source_id_for_alias(alias: str, sources: dict[str, Path]) -> str:
    source_id_aliases = default_policy_registry().source_id_aliases()
    for source_id, runtime_alias in POI_SOURCE_ALIASES.items():
        if runtime_alias == alias and source_id in sources:
            return source_id_aliases.get(source_id, source_id)
    return alias


def _poi_alias_for_source_id(source_id: object) -> str | None:
    text = str(source_id or "").strip()
    if not text:
        return None
    if text in POI_SOURCE_PRIORITY_ORDER:
        return text
    text = default_policy_registry().source_id_aliases().get(text, text)
    return POI_SOURCE_ALIASES.get(text)


def _fill_missing_source_id(frame: gpd.GeoDataFrame, source_id: str) -> gpd.GeoDataFrame:
    result = frame.copy()
    if "source_id" not in result.columns:
        result["source_id"] = source_id
        return result
    missing = result["source_id"].isna() | result["source_id"].astype(str).str.strip().str.len().eq(0)
    result.loc[missing, "source_id"] = source_id
    return result


def _first_present_column(frame: gpd.GeoDataFrame, candidates: tuple[str, ...]) -> pd.Series | None:
    for column in candidates:
        if column in frame.columns:
            return frame[column]
    return None


def _fill_poi_provenance(frame: gpd.GeoDataFrame, *, source_id: str) -> gpd.GeoDataFrame:
    result = _fill_missing_source_id(frame, source_id)
    ids = _first_present_column(result, ("canonical_id", "source_feature_id", "osm_id", "ufi", "uni", "id", "poi_id"))
    names = _first_present_column(result, ("canonical_name", "name", "full_name", "full_nm_nd", "NAME"))
    categories = _first_present_column(result, ("canonical_category", "category", "desig_cd", "generic", "fclass", "type"))

    if "canonical_id" not in result.columns:
        if ids is None:
            result["canonical_id"] = [f"{source_id}:{index}" for index in result.index]
        else:
            result["canonical_id"] = ids.map(lambda value: f"{source_id}:{value}" if pd.notna(value) else None)
    if "canonical_name" not in result.columns:
        result["canonical_name"] = names if names is not None else ""
    if "canonical_category" not in result.columns:
        result["canonical_category"] = categories if categories is not None else ""
    return result


def _role_source_path(
    paths: dict[str, Path],
    *,
    task_kind: str,
    role_id: str,
) -> tuple[str | None, Path | None, dict[str, Any]]:
    registry = default_policy_registry()
    role = registry.source_role_policy(task_kind, role_id)
    aliases = registry.source_runtime_aliases()
    candidates = sorted(
        (item for item in role.get("candidates", []) if isinstance(item, dict)),
        key=lambda item: (int(item.get("priority") or 0), str(item.get("source_id") or "")),
    )
    if not candidates:
        raise KnowledgeReleaseError(f"Source role {task_kind}/{role_id} has no candidates")
    for candidate in candidates:
        source_id = str(candidate.get("source_id") or "").strip()
        if not source_id:
            continue
        path = paths.get(source_id)
        if path is None:
            runtime_alias = aliases.get(source_id)
            path = paths.get(runtime_alias) if runtime_alias else None
        if path is not None:
            return source_id, path, role
    return None, None, role


def _role_is_required(role: dict[str, Any]) -> bool:
    required = role.get("required")
    if not isinstance(required, bool):
        raise KnowledgeReleaseError(
            f"Source role {role.get('task_kind')}/{role.get('role_id')} must declare boolean required"
        )
    return required


def make_building_multisource_runner(
    *,
    raster_sources: dict[str, Path],
    source_priority_order: tuple[str, ...],
) -> DomainRunner:
    def _runner(
        tile: TileSpec,
        sources: dict[str, Path],
        output_dir: Path,
        target_crs: str,
        parameters: dict[str, Any],
    ) -> tuple[Path, dict[str, Any]]:
        inner_tile = TileSpec(
            tile_id=tile.tile_id,
            bbox=tile.working_bbox,
            buffered_bbox=tile.working_buffered_bbox,
            working_bbox=tile.working_bbox,
            working_buffered_bbox=tile.working_buffered_bbox,
            row=tile.row,
            col=tile.col,
        )
        manifest = TileManifest(
            bbox=tile.working_bbox,
            bbox_crs=target_crs,
            working_crs=target_crs,
            tile_width_m=max(tile.working_bbox[2] - tile.working_bbox[0], 1.0),
            tile_height_m=max(tile.working_bbox[3] - tile.working_bbox[1], 1.0),
            overlap_m=0.0,
            tiles=[inner_tile],
        )
        result = TiledBuildingRuntimeService(max_workers=1).run_tiled_multisource_building_job(
            run_id=f"large-area-building-{tile.tile_id}",
            tile_manifest=manifest,
            vector_sources=sources,
            output_dir=output_dir,
            target_crs=target_crs,
            vector_source_crs=target_crs,
            raster_sources=raster_sources,
            source_priority_order=source_priority_order,
            parameters=parameters,
        )
        return result.output_path, {
            "algorithm_id": "algo.fusion.building.multi_source.decomposed.v1",
            "tile_count": result.tile_count,
            "stitched_feature_count": result.stitched_feature_count,
        }

    return _runner


def run_road_tile(
    tile: TileSpec,
    sources: dict[str, Path],
    output_dir: Path,
    target_crs: str,
    parameters: dict[str, Any],
) -> tuple[Path, dict[str, Any]]:
    del tile
    paths = _line_source_paths(sources)
    base_source_id, base_path, _base_role = _role_source_path(
        paths,
        task_kind="road",
        role_id="base_network",
    )
    supplement_source_id, supplement_path, supplement_role = _role_source_path(
        paths,
        task_kind="road",
        role_id="reference_network",
    )
    if base_path is None:
        return _empty_output(output_dir, "road_fused", target_crs), {
            "algorithm_id": "algo.fusion.road.conflation.v7",
            "warning": "missing road source",
        }
    base = _fill_missing_source_id(_read(base_path, target_crs), str(base_source_id))
    if supplement_path is None:
        if _role_is_required(supplement_role):
            return _empty_output(output_dir, "road_fused", target_crs), {
                "algorithm_id": "algo.fusion.road.conflation.v7",
                "warning": "required reference_network source role is unsatisfied",
                "knowledge_refs": ["source_role:road/base_network", "source_role:road/reference_network"],
            }
        output = base
        if "fusion_source" not in output.columns:
            output["fusion_source"] = "base_road_network"
        if "match_role" not in output.columns:
            output["match_role"] = "base_single_source"
        return _write(output, output_dir, "road_fused", target_crs), {
            "algorithm_id": "algo.fusion.road.conflation.v7",
            "stats": {"final_count": int(len(output)), "mode": "single_source_fallback"},
            "warnings": ["missing supplement road source; emitted base road network"],
            "knowledge_refs": ["source_role:road/base_network", "source_role:road/reference_network"],
        }
    supplement = _fill_missing_source_id(_read(supplement_path, target_crs), str(supplement_source_id))
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
        "knowledge_refs": ["source_role:road/base_network", "source_role:road/reference_network"],
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
    base_source_id, base_path, _base_role = _role_source_path(
        paths,
        task_kind="water_polygon",
        role_id="base_water_polygon",
    )
    supplement_source_id, supplement_path, supplement_role = _role_source_path(
        paths,
        task_kind="water_polygon",
        role_id="reference_water_polygon",
    )
    if base_path is None:
        return _empty_output(output_dir, "water_polygon_fused", target_crs, {"source_id": "object", "feature_kind": "object"}), {
            "algorithm_id": "algo.fusion.water_polygon.priority_merge.v2",
            "warning": "missing base water polygon source",
        }
    base = _fill_missing_source_id(_read(base_path, target_crs), str(base_source_id))
    if supplement_path is None:
        if _role_is_required(supplement_role):
            return _empty_output(
                output_dir,
                "water_polygon_fused",
                target_crs,
                {"source_id": "object", "feature_kind": "object"},
            ), {
                "algorithm_id": "algo.fusion.water_polygon.priority_merge.v2",
                "warning": "required reference_water_polygon source role is unsatisfied",
                "knowledge_refs": [
                    "source_role:water_polygon/base_water_polygon",
                    "source_role:water_polygon/reference_water_polygon",
                ],
            }
        if not base.empty:
            base["feature_kind"] = "polygon"
        return _write(base, output_dir, "water_polygon_fused", target_crs), {
            "algorithm_id": "algo.fusion.water_polygon.priority_merge.v2",
            "stats": {"final_count": int(len(base)), "mode": "single_source_fallback"},
            "warnings": ["missing HydroLAKES reference; emitted OSM water polygon baseline"],
            "knowledge_refs": [
                "source_role:water_polygon/base_water_polygon",
                "source_role:water_polygon/reference_water_polygon",
            ],
        }
    supplement = _fill_missing_source_id(_read(supplement_path, target_crs), str(supplement_source_id))
    params = params_from_mapping(WaterPolygonFusionParams, parameters)
    fused = fuse_water_polygons(base, supplement, params)
    if fused.empty:
        fused = gpd.GeoDataFrame(
            {
                "source_id": pd.Series(dtype="object"),
                "feature_kind": pd.Series(dtype="object"),
            },
            geometry=gpd.GeoSeries([], dtype="geometry", crs=target_crs),
            crs=target_crs,
        )
    else:
        fused = fused.set_crs(target_crs) if fused.crs is None else fused.to_crs(target_crs)
        fused["feature_kind"] = "polygon"
    return _write(fused, output_dir, "water_polygon_fused", target_crs), {
        "algorithm_id": "algo.fusion.water_polygon.priority_merge.v2",
        "stats": {"final_count": int(len(fused))},
        "knowledge_refs": [
            "source_role:water_polygon/base_water_polygon",
            "source_role:water_polygon/reference_water_polygon",
        ],
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
    base_source_id, base_path, _base_role = _role_source_path(
        paths,
        task_kind="waterways",
        role_id="base_waterway_line",
    )
    supplement_source_id, supplement_path, supplement_role = _role_source_path(
        paths,
        task_kind="waterways",
        role_id="reference_river_line",
    )
    if base_path is None or (supplement_path is None and _role_is_required(supplement_role)):
        return _empty_output(output_dir, "waterways_fused", target_crs, {"source_id": "object", "feature_kind": "object"}), {
            "algorithm_id": "algo.fusion.waterways.conflation.v7",
            "warning": "missing waterways source",
            "knowledge_refs": [
                "source_role:waterways/base_waterway_line",
                "source_role:waterways/reference_river_line",
            ],
        }
    if supplement_path is None:
        base = _fill_missing_source_id(_read(base_path, target_crs), str(base_source_id))
        base["feature_kind"] = "line"
        return _write(base, output_dir, "waterways_fused", target_crs), {
            "algorithm_id": "algo.fusion.waterways.conflation.v7",
            "stats": {"final_count": int(len(base)), "mode": "single_source_fallback"},
            "warnings": ["missing optional waterways reference; emitted base waterways"],
            "knowledge_refs": [
                "source_role:waterways/base_waterway_line",
                "source_role:waterways/reference_river_line",
            ],
        }
    base = _fill_missing_source_id(_read(base_path, target_crs), str(base_source_id))
    supplement = _fill_missing_source_id(_read(supplement_path, target_crs), str(supplement_source_id))
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
        "knowledge_refs": [
            "source_role:waterways/base_waterway_line",
            "source_role:waterways/reference_river_line",
        ],
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
    _base_source_id, base_path, base_role = _role_source_path(
        paths,
        task_kind="poi",
        role_id="base_poi",
    )
    if base_path is None and _role_is_required(base_role):
        return _empty_output(
            output_dir,
            "poi_fused",
            target_crs,
            {"source_id": "object", "source_rank": "int64", "MATCHED": "bool"},
        ), {
            "algorithm_id": "algo.fusion.poi.geohash_neighbor_match.v1",
            "stats": {"final_count": 0},
            "warning": "required base_poi source role is unsatisfied",
            "knowledge_refs": ["source_role:poi/base_poi"],
        }
    ordered_sources: dict[str, gpd.GeoDataFrame] = {}
    for alias in POI_SOURCE_PRIORITY_ORDER:
        path = paths.get(alias)
        if path is None:
            continue
        source_id = _poi_source_id_for_alias(alias, sources)
        frame = _fill_poi_provenance(_read(path, target_crs), source_id=source_id)
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
    source_id_by_alias = {alias: _poi_source_id_for_alias(alias, sources) for alias in params.source_priority_order}
    if "source_id" not in fused.columns:
        fused["source_id"] = ""
    source_id_text = fused["source_id"].fillna("").astype(str).str.strip()
    missing_source_id = source_id_text.eq("")
    alias_from_source_id = source_id_text.map(_poi_alias_for_source_id)
    if "SRC" in fused.columns:
        source_from_src = fused["SRC"].replace({"base": params.source_priority_order[0]})
        if len(params.source_priority_order) > 1:
            source_from_src = source_from_src.replace({"target": params.source_priority_order[-1]})
        fallback_source_id = source_from_src.map(source_id_by_alias)
        fused.loc[missing_source_id, "source_id"] = fallback_source_id[missing_source_id].fillna("")
        source_id_text = fused["source_id"].fillna("").astype(str).str.strip()
        alias_from_source_id = source_id_text.map(_poi_alias_for_source_id)
        fallback_alias = source_from_src.where(missing_source_id)
        fused["source_rank"] = alias_from_source_id.fillna(fallback_alias).map(rank_by_source).fillna(99).astype(int)
    else:
        fused["source_rank"] = alias_from_source_id.map(rank_by_source).fillna(99).astype(int)
    if "MATCHED" not in fused.columns:
        fused["MATCHED"] = False
    if "canonical_id" not in fused.columns or "canonical_name" not in fused.columns or "canonical_category" not in fused.columns:
        source_id = str(fused["source_id"].iloc[0]) if "source_id" in fused.columns and not fused.empty else "poi"
        fused = _fill_poi_provenance(fused, source_id=source_id)
    stats: dict[str, Any] = {"final_count": int(len(fused)), "source_count": len(ordered_sources)}
    warnings: list[str] = []
    if len(ordered_sources) == 1:
        stats["mode"] = "single_source_fallback"
        warnings.append("missing supplement POI source; emitted available POI source")
    payload: dict[str, Any] = {
        "algorithm_id": "algo.fusion.poi.geohash_neighbor_match.v1",
        "stats": stats,
        "source_priority_order": list(params.source_priority_order),
        "knowledge_refs": ["source_role:poi/base_poi", "source_runtime_priority:poi_vector"],
    }
    if warnings:
        payload["warnings"] = warnings
    return _write(fused, output_dir, "poi_fused", target_crs), payload
