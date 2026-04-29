from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import geopandas as gpd
import pandas as pd

from fusion_algorithms.building_matching_v8 import (
    build_v8_candidate_graph,
    run_cascaded_multi_source_fusion,
)
from fusion_algorithms.building_optimization import (
    optimize_building_conflict_graph,
    optimize_building_road_topology,
    refine_post_conflict_shrink,
    refine_road_tail_conflicts,
    run_building_optimization_chain,
)
from fusion_algorithms.building_raster import enrich_height_from_raster, validate_presence_from_raster
from fusion_algorithms.contracts import (
    BuildingHeightParams,
    BuildingMatchParams,
    BuildingOptimizationParams,
    BuildingRasterPresenceParams,
    RasterSpec,
    SourceSpec,
    params_from_mapping,
)
from fusion_algorithms.quality import detect_spatial_conflicts

if TYPE_CHECKING:
    from agent.executor import ExecutionContext


def _step_slug(context: ExecutionContext, label: str) -> str:
    step = context.active_step if context.active_step is not None else 0
    return f"step_{step:02d}_{label}"


def _write_gdf(gdf: gpd.GeoDataFrame, context: ExecutionContext, label: str) -> Path:
    context.output_dir.mkdir(parents=True, exist_ok=True)
    path = context.output_dir / f"{_step_slug(context, label)}.gpkg"
    gdf.to_file(path, driver="GPKG")
    return path


def _write_json(payload: dict[str, Any], context: ExecutionContext, label: str) -> Path:
    context.output_dir.mkdir(parents=True, exist_ok=True)
    path = context.output_dir / f"{_step_slug(context, label)}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return path


def _latest_vector_path(context: ExecutionContext) -> Path:
    if context.active_step is not None:
        for step in range(context.active_step - 1, 0, -1):
            path = context.intermediate_artifacts.get(f"step:{step}")
            if path is not None and path.suffix.lower() in {".gpkg", ".shp", ".geojson"}:
                return path
    if context.intermediate_artifacts:
        for path in reversed(list(context.intermediate_artifacts.values())):
            if path.suffix.lower() in {".gpkg", ".shp", ".geojson"}:
                return path
    return context.ref_shp if context.ref_shp.exists() else context.osm_shp


def _read_latest_vector(context: ExecutionContext) -> gpd.GeoDataFrame:
    return gpd.read_file(_latest_vector_path(context))


def _source_specs_from_context(context: ExecutionContext) -> list[SourceSpec]:
    if context.named_vectors:
        return [
            SourceSpec(name=name, path=path, priority=idx)
            for idx, (name, path) in enumerate(context.named_vectors.items(), start=1)
        ]
    return [
        SourceSpec(name="OSM", path=context.osm_shp, priority=1),
        SourceSpec(name="REF", path=context.ref_shp, priority=2),
    ]


def _read_source_map(context: ExecutionContext) -> dict[str, gpd.GeoDataFrame]:
    source_map: dict[str, gpd.GeoDataFrame] = {}
    for spec in _source_specs_from_context(context):
        if not Path(spec.path).exists():
            continue
        frame = gpd.read_file(spec.path)
        if frame.crs is None:
            frame = frame.set_crs(context.target_crs)
        source_map[spec.name] = frame.to_crs(context.target_crs)
    return source_map


def _read_roads(context: ExecutionContext) -> gpd.GeoDataFrame | None:
    road_path = context.context_vectors.get("roads") or context.named_vectors.get("ROADS")
    if road_path is None or not Path(road_path).exists():
        return None
    roads = gpd.read_file(road_path)
    if roads.crs is None:
        roads = roads.set_crs(context.target_crs)
    return roads.to_crs(context.target_crs)


def _match_params(context: ExecutionContext, source_names: tuple[str, ...] | None = None) -> BuildingMatchParams:
    values = dict(context.step_parameters or {})
    if source_names and "source_priority_order" not in values:
        values["source_priority_order"] = source_names
    if isinstance(values.get("source_priority_order"), list):
        values["source_priority_order"] = tuple(values["source_priority_order"])
    return params_from_mapping(BuildingMatchParams, values)


def _presence_params(context: ExecutionContext) -> BuildingRasterPresenceParams:
    return params_from_mapping(BuildingRasterPresenceParams, context.step_parameters)


def _height_params(context: ExecutionContext) -> BuildingHeightParams:
    return params_from_mapping(BuildingHeightParams, context.step_parameters)


def _optimization_params(context: ExecutionContext) -> BuildingOptimizationParams:
    return params_from_mapping(BuildingOptimizationParams, context.step_parameters)


def run_building_source_normalize(context: ExecutionContext) -> Path:
    frames = []
    for name, frame in _read_source_map(context).items():
        normalized = frame[frame.geometry.notna() & ~frame.geometry.is_empty].copy()
        normalized["source_name"] = name
        frames.append(normalized)
    if not frames:
        raise ValueError("No building vector sources were available for normalization.")
    combined = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs=context.target_crs)
    return _write_gdf(combined, context, "building_source_normalize")


def run_building_presence_raster(context: ExecutionContext) -> Path:
    raster_path = context.named_rasters.get("building_presence")
    frame = _read_latest_vector(context)
    if raster_path is None:
        frame["presence_status"] = "not_evaluated_missing_raster"
        return _write_gdf(frame, context, "building_presence_missing_raster")
    output = validate_presence_from_raster(
        frame,
        RasterSpec(kind="building_presence", path=raster_path),
        _presence_params(context),
    )
    return _write_gdf(output, context, "building_presence_raster")


def run_building_height_from_raster(context: ExecutionContext) -> Path:
    raster_path = context.named_rasters.get("building_height")
    frame = _read_latest_vector(context)
    if raster_path is None:
        frame["height_status"] = "not_evaluated_missing_raster"
        return _write_gdf(frame, context, "building_height_missing_raster")
    output = enrich_height_from_raster(
        frame,
        RasterSpec(kind="building_height", path=raster_path),
        _height_params(context),
    )
    return _write_gdf(output, context, "building_height_from_raster")


def run_building_v8_candidate_graph(context: ExecutionContext) -> Path:
    sources = _read_source_map(context)
    names = tuple(sources.keys())
    if len(names) < 2:
        raise ValueError("V8 candidate graph needs at least two building sources.")
    graph = build_v8_candidate_graph(
        sources[names[0]],
        sources[names[1]],
        _read_roads(context),
        _match_params(context, names),
        base_name=names[0],
        target_name=names[1],
    )
    return _write_json({"edges": graph.edges.to_dict("records"), "base": names[0], "target": names[1]}, context, "building_v8_candidate_graph")


def run_building_multi_source_decomposed(context: ExecutionContext) -> Path:
    sources = _read_source_map(context)
    if len(sources) < 2:
        raise ValueError("Multi-source building fusion needs at least two building sources.")
    names = tuple(sources.keys())
    params = _match_params(context, names)
    roads = _read_roads(context)
    try:
        fused = run_cascaded_multi_source_fusion(sources, roads, params, source_priority_order=params.source_priority_order)
    except ModuleNotFoundError:
        frames = []
        for name in params.source_priority_order:
            if name in sources:
                frame = sources[name].copy()
                frame["fusion_source"] = name
                frames.append(frame)
        fused = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs=context.target_crs)
        fused["fusion_runtime_mode"] = "fallback_missing_dependency"
    return _write_gdf(fused, context, "building_multi_source_decomposed")


def run_building_road_topology(context: ExecutionContext) -> Path:
    frame = _read_latest_vector(context)
    output = optimize_building_road_topology(frame, _read_roads(context), _optimization_params(context))
    return _write_gdf(output, context, "building_road_topology")


def run_building_conflict_graph(context: ExecutionContext) -> Path:
    frame = _read_latest_vector(context)
    try:
        output = optimize_building_conflict_graph(frame, _read_roads(context), _optimization_params(context))
    except ModuleNotFoundError:
        output = frame.copy()
        output["optimization_status"] = "not_evaluated_missing_dependency"
    return _write_gdf(output, context, "building_conflict_graph")


def run_building_post_conflict_shrink(context: ExecutionContext) -> Path:
    frame = _read_latest_vector(context)
    output, summary = refine_post_conflict_shrink(frame, _optimization_params(context))
    output["post_shrink_summary"] = json.dumps(summary, ensure_ascii=False)
    return _write_gdf(output, context, "building_post_conflict_shrink")


def run_building_road_tail(context: ExecutionContext) -> Path:
    frame = _read_latest_vector(context)
    output, summary = refine_road_tail_conflicts(frame, _read_roads(context), _optimization_params(context))
    output["road_tail_summary"] = json.dumps(summary, ensure_ascii=False)
    return _write_gdf(output, context, "building_road_tail")


def run_building_quality_metrics(context: ExecutionContext) -> Path:
    frame = _read_latest_vector(context)
    conflicts = detect_spatial_conflicts(frame)
    return _write_json(
        {
            "feature_count": int(len(frame)),
            "conflict_count": int(len(conflicts)),
            "conflicts": conflicts[:100],
        },
        context,
        "building_quality_metrics",
    )


def run_building_optimization_composite(context: ExecutionContext) -> Path:
    frame = _read_latest_vector(context)
    try:
        output, lineage = run_building_optimization_chain(frame, _read_roads(context), _optimization_params(context))
    except ModuleNotFoundError:
        output = frame.copy()
        output["optimization_status"] = "not_evaluated_missing_dependency"
        lineage = {"runtime_mode": "fallback_missing_dependency"}
    path = _write_gdf(output, context, "building_optimization_chain")
    _write_json(lineage, context, "building_optimization_lineage")
    return path


def run_passthrough_latest_vector(context: ExecutionContext, label: str) -> Path:
    return _write_gdf(_read_latest_vector(context), context, label)
