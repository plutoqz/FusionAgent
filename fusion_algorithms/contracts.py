from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional


def _path(value: str | Path) -> Path:
    return value if isinstance(value, Path) else Path(value)


@dataclass(frozen=True)
class SourceSpec:
    name: str
    path: str | Path
    priority: int = 100
    data_type: str = "vector"
    role: str = "primary"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self.name.strip().upper())
        object.__setattr__(self, "path", _path(self.path))


@dataclass(frozen=True)
class RasterSpec:
    kind: str
    path: str | Path
    band: int = 1
    nodata: Optional[float] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", self.kind.strip().lower())
        object.__setattr__(self, "path", _path(self.path))


@dataclass(frozen=True)
class VectorArtifact:
    data_type_id: str
    path: Path
    source_name: str | None = None
    crs: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LineageRecord:
    algorithm_id: str
    inputs: tuple[str, ...] = ()
    parameters: Mapping[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class QualitySummary:
    metric_name: str
    values: Mapping[str, Any] = field(default_factory=dict)
    lineage: tuple[LineageRecord, ...] = ()


@dataclass(frozen=True)
class AlgorithmStepContext:
    run_id: str
    algorithm_id: str
    output_dir: Path
    parameters: Mapping[str, Any] = field(default_factory=dict)
    named_vectors: Mapping[str, Path] = field(default_factory=dict)
    named_rasters: Mapping[str, Path] = field(default_factory=dict)
    context_vectors: Mapping[str, Path] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildingRasterPresenceParams:
    prob_threshold: float = 0.20
    search_dist_m: float = 4.0
    height_thresh: float = 2.0
    n_jobs: int = -1
    confirmed_score_threshold: float = 0.55
    confirmed_p90_threshold: float = 0.45
    confirmed_support_threshold: float = 0.50
    uncertain_score_threshold: float = 0.30
    uncertain_max_threshold: float = 0.45
    uncertain_support_threshold: float = 0.15
    status_field: str = "exist_status"
    keep_uncertain: bool = True


@dataclass(frozen=True)
class BuildingHeightParams:
    height_sampling_method: str = "fusioncode_resolution_aware"
    n_jobs: int = -1
    height_output_field: str = "H_Raster"
    canonical_height_field: str = "height"
    positive_only: bool = True
    fallback_height: float = 0.0
    preserve_original_crs: bool = True


@dataclass(frozen=True)
class BuildingMatchParams:
    parallel_backend: str = "process"
    workers: int | None = None
    shift_anchor_iou: float = 0.40
    shift_grid_size: float = 300.0
    max_shift_residual_norm: float = 6.0
    enable_anchor_recall: bool = True
    anchor_min_groups: int = 1
    anchor_recall_min_group_score: float = 0.42
    anchor_recall_max_shift_m: float = 12.0
    anchor_recall_min_cover: float = 0.20
    anchor_recall_min_iou: float = 0.10
    anchor_recall_min_explain: float = 0.24
    anchor_recall_min_area_ratio: float = 0.28
    anchor_recall_min_fit: float = 0.30
    fan_min_cover_small: float = 0.20
    fan_min_iou_fallback: float = 0.10
    weak_min_cover: float = 0.05
    weak_min_iou: float = 0.05
    enable_road_cut: bool = True
    road_highway_col: str = "highway"
    major_roads: tuple[str, ...] = ("motorway", "trunk", "primary", "secondary")
    exemption_cover_small: float = 0.15
    lock_single_min_strict_score: float = 0.46
    lock_single_min_cover: float = 0.32
    lock_single_min_iou: float = 0.20
    lock_single_min_fit: float = 0.35
    lock_single_min_area_ratio: float = 0.28
    lock_single_min_mutual_explain: float = 0.26
    lock_mutual_min_gap: float = 0.15
    lock_mutual_min_adv_ratio: float = 2.50
    thresh_1_to_1: float = 0.40
    thresh_1_to_N: float = 0.44
    thresh_M_to_N: float = 0.47
    large_group_penalty: float = 0.005
    max_dynamic_threshold: float = 0.58
    min_closure_accept_1to1: float = 0.30
    min_closure_accept_multi: float = 0.25
    min_purity_accept_multi: float = 0.12
    min_coarse_accept_multi: float = 0.18
    min_detail_accept_multi: float = 0.18
    min_macro_iou_accept_multi: float = 0.20
    min_explain_accept_multi: float = 0.25
    max_dominant_edge_ratio: float = 0.85
    max_weak_member_ratio: float = 0.40
    min_support_accept_1to1: float = 0.36
    min_fit_accept_1to1: float = 0.30
    min_explain_accept_1to1: float = 0.24
    min_macro_iou_accept_1to1: float = 0.18
    min_support_accept_multi: float = 0.30
    source_priority_order: tuple[str, ...] = ("MS", "GG", "OSM")
    name_aliases: tuple[str, ...] = ("name", "Name", "NAME", "bld_name", "building_n")
    height_aliases: tuple[str, ...] = ("height", "Height", "HEIGHT", "building_h", "bld_h", "H_Raster")
    levels_aliases: tuple[str, ...] = ("levels", "Levels", "LEVELS", "floors", "num_floors", "building_l")
    class_aliases: tuple[str, ...] = ("building", "type", "class", "use", "function", "CATEGORY")
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BuildingOptimizationParams:
    global_max_shift: float = 4.0
    global_area_change_limit: float = 0.10
    simplify_tol: float = 0.3
    cluster_tol: float = 2.0
    snap_tol: float = 0.5
    neighbor_search_radius: float = 30.0
    neighbor_max_k: int = 0
    overlap_delete_threshold: float = 0.75
    overlap_min_area: float = 0.0
    road_buffer_width: float = 0.1
    max_tolerable_depth: float = 2.5
    w_overlap: float = 2797.45
    w_neighbor_barrier: float = 98.97
    w_road_expulsion: float = 4267.96
    w_road_barrier: float = 6000.0
    max_translate: float = 20.0
    min_scale: float = 0.85
    max_scale: float = 1.00
    max_nfev: int = 30
    ftol: float = 1e-3
    n_jobs: int = -1
    max_outer_iterations: int = 3
    enable_post_conflict_shrink: bool = True
    post_shrink_threshold_m2: float = 5.0
    post_shrink_scale_cap_pct: float = 0.05
    post_shrink_scale_step_pct: float = 0.005
    tail_conflict_max_area: float = 2.0
    tail_translate_limit: float = 1.0
    tail_min_scale: float = 0.92
    tail_max_scale: float = 1.00
    tail_max_iterations: int = 3


@dataclass(frozen=True)
class RoadFusionParams:
    angle_threshold_deg: int = 135
    snap_tolerance_m: float = 1.0
    buffer_dist_m: float = 20.0
    max_hausdorff_m: float = 15.0
    dedupe_buffer_m: float = 15.0
    endpoint_buffer_radius_m: float = 15.0
    angle_diff_max_deg: float = 45.0
    min_length_similarity: float = 0.2
    line_priority_order: tuple[str, ...] = ("OSM", "MS", "REF")


@dataclass(frozen=True)
class WaterLineFusionParams(RoadFusionParams):
    line_priority_order: tuple[str, ...] = ("OSM", "MS", "GNG")


@dataclass(frozen=True)
class WaterPolygonFusionParams:
    overlap_threshold: float = 0.1
    min_intersection_area: float = 0.0
    source_priority_order: tuple[str, ...] = ("OSM", "NEW", "REF")
    preserve_unmatched_osm: bool = True
    preserve_unmatched_new: bool = True


@dataclass(frozen=True)
class PoiFusionParams:
    geohash_precision: int = 8
    neighbor_rings: int = 1
    name_similarity_threshold: float = 0.75
    source_priority_order: tuple[str, ...] = ("GOOGLE", "GNG", "OSM", "RH")
    duplicate_distance_m: float = 250.0
    remaining_output_mode: str = "separate"


@dataclass(frozen=True)
class ConflictDetectionParams:
    geometry_type_scope: str = "polygon"
    buffer_distance_m: float = 0.0
    overlap_area_min: float = 0.0
    touch_policy: str = "ignore_touches"
    report_fields: tuple[str, ...] = ("left_id", "right_id", "overlap_area")


def params_from_mapping(cls: type, values: Mapping[str, Any] | None) -> Any:
    values = dict(values or {})
    allowed = getattr(cls, "__dataclass_fields__", {})
    return cls(**{key: value for key, value in values.items() if key in allowed})


def dataclass_to_dict(value: Any) -> Dict[str, Any]:
    fields = getattr(value, "__dataclass_fields__", {})
    return {key: getattr(value, key) for key in fields}
