from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib.util
from pathlib import Path
import sys
from typing import Any

import geopandas as gpd
import pandas as pd


_RUNTIME_MODULE_NAME = "fusion_algorithms._road_v7_runtime"
_RUNTIME_SCRIPT_PATH = Path(__file__).resolve().parents[1] / "Algorithm" / "road_fusion_optimized_v7.py"
_RUNTIME_MODULE = None


def _runtime():
    global _RUNTIME_MODULE
    if _RUNTIME_MODULE is not None:
        return _RUNTIME_MODULE
    if _RUNTIME_MODULE_NAME in sys.modules:
        _RUNTIME_MODULE = sys.modules[_RUNTIME_MODULE_NAME]
        return _RUNTIME_MODULE
    spec = importlib.util.spec_from_file_location(_RUNTIME_MODULE_NAME, _RUNTIME_SCRIPT_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load V7 runtime module from {_RUNTIME_SCRIPT_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_RUNTIME_MODULE_NAME] = module
    spec.loader.exec_module(module)
    _RUNTIME_MODULE = module
    return module


@dataclass
class LineConflationV7Config:
    target_crs: str = "EPSG:32643"
    do_split_by_angle: bool = True
    angle_threshold: float = 135.0
    max_segment_length: float | None = 800.0
    match_buffer_dist: float = 20.0
    max_hausdorff: float = 15.0
    loose_angle_threshold: float = 45.0
    min_len_similarity: float = 0.05
    min_supplement_coverage_for_matched: float = 0.80
    preserve_matched_supplement_residuals: bool = True
    min_residual_length: float = 10.0
    assume_missing_crs_as_target: bool = False
    duplicate_buffer_dist: float = 10.0
    duplicate_coverage_threshold: float = 0.92
    duplicate_angle_threshold: float = 25.0
    duplicate_max_centerline_dist: float = 8.0
    enable_group_duplicate_removal: bool = True
    group_duplicate_buffer_dist: float = 6.0
    group_duplicate_coverage_threshold: float = 0.90
    group_duplicate_angle_threshold: float = 18.0
    group_duplicate_mean_distance: float = 4.0
    group_duplicate_p90_distance: float = 7.0
    duplicate_sample_step: float = 30.0
    enable_near_base_return_pruning: bool = True
    near_base_return_endpoint_radius: float = 12.0
    near_base_return_corridor_dist: float = 12.0
    near_base_return_coverage_threshold: float = 0.85
    near_base_return_mean_distance: float = 6.0
    near_base_return_p90_distance: float = 10.0
    near_base_return_max_distance: float = 16.0
    near_base_return_sample_step: float = 30.0
    enable_crossing_duplicate_pruning: bool = True
    crossing_corridor_dist: float = 12.0
    crossing_coverage_threshold: float = 0.82
    crossing_mean_distance: float = 6.0
    crossing_p90_distance: float = 10.0
    crossing_max_distance: float = 18.0
    crossing_angle_threshold: float = 22.0
    crossing_touch_tolerance: float = 1.0
    crossing_sample_step: float = 30.0
    endpoint_snap_radius: float = 10.0
    min_length_after_snap: float = 1.0
    max_endpoint_snap_bend_angle: float = 35.0
    enable_dangle_cleanup: bool = True
    dangle_connect_radius: float = 10.0
    dangle_delete_two_free_max_length: float = 30.0
    dangle_delete_one_free_max_length: float = 12.0
    min_line_length: float = 0.05
    log_every_n: int = 1000
    cleanup_mode: str = "quality"
    run_second_clean_pass: bool = True
    output_crs: str | None = None

    def to_runtime_config(self):
        runtime = _runtime()
        return runtime.RoadFusionConfig(
            target_crs=self.target_crs,
            do_split_by_angle=self.do_split_by_angle,
            angle_threshold=self.angle_threshold,
            max_segment_length=self.max_segment_length,
            match_buffer_dist=self.match_buffer_dist,
            max_hausdorff=self.max_hausdorff,
            loose_angle_threshold=self.loose_angle_threshold,
            min_len_similarity=self.min_len_similarity,
            min_msft_coverage_for_matched=self.min_supplement_coverage_for_matched,
            preserve_matched_msft_residuals=self.preserve_matched_supplement_residuals,
            min_residual_length=self.min_residual_length,
            assume_missing_crs_as_target=self.assume_missing_crs_as_target,
            duplicate_buffer_dist=self.duplicate_buffer_dist,
            duplicate_coverage_threshold=self.duplicate_coverage_threshold,
            duplicate_angle_threshold=self.duplicate_angle_threshold,
            duplicate_max_centerline_dist=self.duplicate_max_centerline_dist,
            enable_group_duplicate_removal=self.enable_group_duplicate_removal,
            group_duplicate_buffer_dist=self.group_duplicate_buffer_dist,
            group_duplicate_coverage_threshold=self.group_duplicate_coverage_threshold,
            group_duplicate_angle_threshold=self.group_duplicate_angle_threshold,
            group_duplicate_mean_distance=self.group_duplicate_mean_distance,
            group_duplicate_p90_distance=self.group_duplicate_p90_distance,
            duplicate_sample_step=self.duplicate_sample_step,
            enable_near_base_return_pruning=self.enable_near_base_return_pruning,
            near_base_return_endpoint_radius=self.near_base_return_endpoint_radius,
            near_base_return_corridor_dist=self.near_base_return_corridor_dist,
            near_base_return_coverage_threshold=self.near_base_return_coverage_threshold,
            near_base_return_mean_distance=self.near_base_return_mean_distance,
            near_base_return_p90_distance=self.near_base_return_p90_distance,
            near_base_return_max_distance=self.near_base_return_max_distance,
            near_base_return_sample_step=self.near_base_return_sample_step,
            enable_crossing_duplicate_pruning=self.enable_crossing_duplicate_pruning,
            crossing_corridor_dist=self.crossing_corridor_dist,
            crossing_coverage_threshold=self.crossing_coverage_threshold,
            crossing_mean_distance=self.crossing_mean_distance,
            crossing_p90_distance=self.crossing_p90_distance,
            crossing_max_distance=self.crossing_max_distance,
            crossing_angle_threshold=self.crossing_angle_threshold,
            crossing_touch_tolerance=self.crossing_touch_tolerance,
            crossing_sample_step=self.crossing_sample_step,
            endpoint_snap_radius=self.endpoint_snap_radius,
            min_length_after_snap=self.min_length_after_snap,
            max_endpoint_snap_bend_angle=self.max_endpoint_snap_bend_angle,
            enable_dangle_cleanup=self.enable_dangle_cleanup,
            dangle_connect_radius=self.dangle_connect_radius,
            dangle_delete_two_free_max_length=self.dangle_delete_two_free_max_length,
            dangle_delete_one_free_max_length=self.dangle_delete_one_free_max_length,
            min_line_length=self.min_line_length,
            log_every_n=self.log_every_n,
            cleanup_mode=self.cleanup_mode,
            run_second_clean_pass=self.run_second_clean_pass,
            output_crs=self.output_crs,
        )


@dataclass
class LineConflationResult:
    frame: gpd.GeoDataFrame
    stats: dict[str, Any]
    config: dict[str, Any]
    lineage: dict[str, Any]
    warnings: list[str]


def _load_frame(source: gpd.GeoDataFrame | Path | str) -> gpd.GeoDataFrame:
    if isinstance(source, gpd.GeoDataFrame):
        return source.copy()
    return gpd.read_file(source)


def _pick_existing_column(frame: gpd.GeoDataFrame, candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate
    return None


def _ensure_identifier_column(
    frame: gpd.GeoDataFrame,
    *,
    required_column: str,
    candidates: tuple[str, ...],
) -> gpd.GeoDataFrame:
    prepared = frame.copy()
    if required_column in prepared.columns:
        return prepared
    selected = _pick_existing_column(prepared, candidates)
    if selected is None:
        prepared[required_column] = pd.Series(range(1, len(prepared) + 1), index=prepared.index, dtype="int64")
        return prepared
    prepared[required_column] = prepared[selected].fillna("").astype(str)
    return prepared


def _coalesce_columns(
    frame: gpd.GeoDataFrame,
    *,
    target_column: str,
    candidates: tuple[str, ...],
    default: str,
) -> gpd.GeoDataFrame:
    prepared = frame.copy()
    if target_column in prepared.columns and prepared[target_column].notna().any():
        return prepared
    selected = _pick_existing_column(prepared, candidates)
    if selected is None:
        prepared[target_column] = default
    else:
        prepared[target_column] = prepared[selected].fillna(default)
    return prepared


def _rename_stats(stats: dict[str, Any]) -> dict[str, Any]:
    replacements = {
        "osm_segments": "base_segments",
        "msft_segments": "supplement_segments",
        "matched_msft_segments": "matched_supplement_segments",
        "unmatched_msft_segments": "unmatched_supplement_segments",
        "residual_msft_segments": "residual_supplement_segments",
        "supplemented_msft_segments": "supplemented_segments",
        "residual_msft_total_length": "residual_supplement_total_length",
        "dangling_ms_road_removed": "dangling_supplement_removed",
    }
    renamed: dict[str, Any] = {}
    for key, value in stats.items():
        renamed[replacements.get(key, key)] = value
    return renamed


def _remove_duplicate_supplement_segments(
    fused: gpd.GeoDataFrame,
    runtime_cfg,
) -> tuple[gpd.GeoDataFrame, int]:
    if fused.empty or "fclass" not in fused.columns:
        return fused, 0
    supplements = fused[
        fused["fclass"].eq("ms_road")
        & ~fused.get("residual_from_matched", pd.Series(False, index=fused.index)).fillna(False).astype(bool)
    ].copy()
    if len(supplements) <= 1:
        return fused, 0

    runtime = _runtime()
    working = supplements[
        supplements.geometry.notna()
        & ~supplements.geometry.is_empty
        & supplements.geometry.geom_type.isin(["LineString", "MultiLineString"])
    ].copy()
    if len(working) <= 1:
        return fused, 0

    working = working.reset_index()
    sindex = working.sindex
    geoms = working.geometry.to_numpy()
    lengths = working.geometry.length.to_numpy()
    angles = [runtime.line_angle(geom) for geom in geoms]
    drop_positions: set[int] = set()

    for i, geom_a in enumerate(geoms):
        if i in drop_positions or geom_a is None or geom_a.is_empty:
            continue
        search_bounds = runtime.expanded_bounds(geom_a.bounds, runtime_cfg.duplicate_buffer_dist)
        for candidate in sindex.intersection(search_bounds):
            j = int(candidate)
            if j <= i or j in drop_positions:
                continue
            geom_b = geoms[j]
            if geom_b is None or geom_b.is_empty:
                continue
            if runtime.is_duplicate_supplement(geom_a, geom_b, angles[i], angles[j], runtime_cfg):
                if lengths[j] <= lengths[i]:
                    drop_positions.add(j)
                else:
                    drop_positions.add(i)
                    break
            elif runtime.is_duplicate_supplement(geom_b, geom_a, angles[j], angles[i], runtime_cfg):
                if lengths[i] <= lengths[j]:
                    drop_positions.add(i)
                    break
                drop_positions.add(j)

    if not drop_positions:
        return fused, 0
    drop_indexes = set(working.iloc[list(drop_positions)]["index"].tolist())
    cleaned = fused.drop(index=sorted(drop_indexes)).reset_index(drop=True)
    return gpd.GeoDataFrame(cleaned, geometry=fused.geometry.name, crs=fused.crs), len(drop_indexes)


def run_line_conflation_v7(
    base: gpd.GeoDataFrame | Path | str,
    supplement: gpd.GeoDataFrame | Path | str,
    *,
    config: LineConflationV7Config,
    algorithm_id: str,
    base_id_candidates: tuple[str, ...] = ("osm_id", "id", "source_feature_id", "objectid", "fid"),
    supplement_id_candidates: tuple[str, ...] = ("FID_1", "id", "source_feature_id", "osm_id", "objectid", "fid"),
    base_class_candidates: tuple[str, ...] = ("fclass",),
    supplement_class_candidates: tuple[str, ...] = ("fclass",),
    default_base_class: str = "base",
    default_supplement_class: str = "supplement",
) -> LineConflationResult:
    runtime = _runtime()
    runtime_cfg = config.to_runtime_config()

    base_frame = _ensure_identifier_column(_load_frame(base), required_column="osm_id", candidates=base_id_candidates)
    base_frame = _coalesce_columns(
        base_frame,
        target_column="fclass",
        candidates=base_class_candidates,
        default=default_base_class,
    )
    supplement_frame = _ensure_identifier_column(
        _load_frame(supplement),
        required_column="FID_1",
        candidates=supplement_id_candidates,
    )
    supplement_frame = _coalesce_columns(
        supplement_frame,
        target_column="fclass",
        candidates=supplement_class_candidates,
        default=default_supplement_class,
    )

    prepared_base = runtime.prepare_osm(base_frame, runtime_cfg)
    prepared_supplement = runtime.prepare_msft(supplement_frame, runtime_cfg)

    fused, raw_stats = runtime.match_and_fuse_fast(prepared_base, prepared_supplement, runtime_cfg)
    residual_mask = fused.get("residual_from_matched", pd.Series(False, index=fused.index)).fillna(False).astype(bool)
    protected_residuals = fused[residual_mask].copy()
    fused = fused[~residual_mask].copy()
    cleanup_mode = runtime.resolved_cleanup_mode(runtime_cfg)

    fused, removed_self_duplicates = _remove_duplicate_supplement_segments(fused, runtime_cfg)
    raw_stats["duplicate_removed_before_snap"] = int(removed_self_duplicates)

    fused, removed_before_snap = runtime.remove_duplicate_ms_roads_fast(fused, runtime_cfg)
    raw_stats["duplicate_removed_before_snap"] += int(removed_before_snap)

    fused, removed_group_before_snap = runtime.remove_duplicate_ms_roads_group_fast(fused, runtime_cfg)
    raw_stats["group_duplicate_removed_before_snap"] = int(removed_group_before_snap)

    raw_stats["near_base_return_removed_before_snap"] = 0
    raw_stats["crossing_duplicate_removed_before_snap"] = 0
    raw_stats["duplicate_removed_after_snap"] = 0
    raw_stats["group_duplicate_removed_after_snap"] = 0
    raw_stats["near_base_return_removed_after_snap"] = 0
    raw_stats["crossing_duplicate_removed_after_snap"] = 0

    if cleanup_mode in {"quality", "balanced"}:
        fused, removed_near_base_before_snap = runtime.prune_near_base_return_ms_roads(fused, runtime_cfg)
        raw_stats["near_base_return_removed_before_snap"] = int(removed_near_base_before_snap)
        fused, removed_crossing_before_snap = runtime.prune_crossing_duplicate_ms_roads(fused, runtime_cfg)
        raw_stats["crossing_duplicate_removed_before_snap"] = int(removed_crossing_before_snap)

    fused = runtime.adjust_ms_endpoints_to_base(fused, runtime_cfg)

    if cleanup_mode in {"quality", "balanced"}:
        fused, removed_after_snap = runtime.remove_duplicate_ms_roads_fast(
            fused,
            runtime_cfg,
            coverage_threshold=max(runtime_cfg.duplicate_coverage_threshold, 0.95),
            max_centerline_dist=min(runtime_cfg.duplicate_max_centerline_dist, 5.0),
        )
        raw_stats["duplicate_removed_after_snap"] = int(removed_after_snap)
        fused, removed_group_after_snap = runtime.remove_duplicate_ms_roads_group_fast(
            fused,
            runtime_cfg,
            coverage_threshold=max(runtime_cfg.group_duplicate_coverage_threshold, 0.95),
            mean_distance_threshold=min(runtime_cfg.group_duplicate_mean_distance, 3.0),
            p90_distance_threshold=min(runtime_cfg.group_duplicate_p90_distance, 5.0),
        )
        raw_stats["group_duplicate_removed_after_snap"] = int(removed_group_after_snap)

    if cleanup_mode in {"quality", "fast"}:
        fused, removed_near_base_after_snap = runtime.prune_near_base_return_ms_roads(
            fused,
            runtime_cfg,
            coverage_threshold=max(runtime_cfg.near_base_return_coverage_threshold, 0.90),
            mean_distance_threshold=min(runtime_cfg.near_base_return_mean_distance, 5.0),
            p90_distance_threshold=min(runtime_cfg.near_base_return_p90_distance, 8.0),
            max_distance_threshold=min(runtime_cfg.near_base_return_max_distance, 14.0),
        )
        raw_stats["near_base_return_removed_after_snap"] = int(removed_near_base_after_snap)
        fused, removed_crossing_after_snap = runtime.prune_crossing_duplicate_ms_roads(
            fused,
            runtime_cfg,
            coverage_threshold=max(runtime_cfg.crossing_coverage_threshold, 0.88),
            mean_distance_threshold=min(runtime_cfg.crossing_mean_distance, 5.0),
            p90_distance_threshold=min(runtime_cfg.crossing_p90_distance, 8.0),
            max_distance_threshold=min(runtime_cfg.crossing_max_distance, 14.0),
        )
        raw_stats["crossing_duplicate_removed_after_snap"] = int(removed_crossing_after_snap)

    fused, removed_dangles = runtime.cleanup_dangling_ms_roads(fused, runtime_cfg)
    raw_stats["dangling_ms_road_removed"] = int(removed_dangles)

    if not protected_residuals.empty:
        fused = gpd.GeoDataFrame(
            pd.concat([fused, protected_residuals], ignore_index=True),
            geometry=fused.geometry.name,
            crs=fused.crs,
        )
    raw_stats["final_count"] = int(len(fused))

    if config.output_crs:
        fused = fused.to_crs(config.output_crs)

    return LineConflationResult(
        frame=fused.reset_index(drop=True),
        stats=_rename_stats(raw_stats),
        config=asdict(config),
        lineage={
            "algorithm_id": algorithm_id,
            "base_input_kind": "path" if not isinstance(base, gpd.GeoDataFrame) else "geodataframe",
            "supplement_input_kind": "path" if not isinstance(supplement, gpd.GeoDataFrame) else "geodataframe",
        },
        warnings=[],
    )
