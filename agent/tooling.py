from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass(frozen=True)
class ToolSpec:
    algorithm_id: str
    input_types: tuple[str, ...]
    output_type: str
    handler_name: str
    timeout_seconds: int = 600
    retry_count: int = 0
    error_policy: dict[str, str] = field(default_factory=lambda: {"missing_handler": "fail_closed"})


class ToolRegistry:
    def __init__(self, specs: list[ToolSpec]) -> None:
        self._specs: Dict[str, ToolSpec] = {}
        for spec in specs:
            if spec.algorithm_id in self._specs:
                raise ValueError(f"Duplicate tool spec for algorithm: {spec.algorithm_id}")
            self._specs[spec.algorithm_id] = spec

    def get(self, algorithm_id: str) -> Optional[ToolSpec]:
        return self._specs.get(algorithm_id)

    def require(self, algorithm_id: str) -> ToolSpec:
        spec = self.get(algorithm_id)
        if spec is None:
            raise ValueError(f"Unknown algorithm in tool registry: {algorithm_id}")
        return spec

    def list_algorithm_ids(self) -> list[str]:
        return sorted(self._specs)


def build_default_tool_registry() -> ToolRegistry:
    return ToolRegistry(
        [
            ToolSpec(
                algorithm_id="algo.fusion.building.v1",
                input_types=("dt.building.bundle",),
                output_type="dt.building.fused",
                handler_name="_handle_building",
            ),
            ToolSpec(
                algorithm_id="algo.fusion.building.safe",
                input_types=("dt.building.bundle",),
                output_type="dt.building.fused",
                handler_name="_handle_building_safe",
            ),
            ToolSpec(
                algorithm_id="algo.fusion.road.v1",
                input_types=("dt.road.bundle",),
                output_type="dt.road.fused",
                handler_name="_handle_road",
            ),
            ToolSpec(
                algorithm_id="algo.fusion.road.safe",
                input_types=("dt.road.bundle",),
                output_type="dt.road.fused",
                handler_name="_handle_road",
            ),
            ToolSpec(
                algorithm_id="algo.fusion.water.v1",
                input_types=("dt.water.bundle",),
                output_type="dt.water.fused",
                handler_name="_handle_water",
            ),
            ToolSpec(
                algorithm_id="algo.fusion.poi.v1",
                input_types=("dt.poi.bundle",),
                output_type="dt.poi.fused",
                handler_name="_handle_poi",
            ),
            ToolSpec(
                algorithm_id="algo.transform.trajectory_to_road_candidate",
                input_types=("dt.trajectory.raw",),
                output_type="dt.road.candidate",
                handler_name="_handle_reserved_trajectory_pretransform",
                error_policy={"missing_handler": "fail_closed", "reserved": "true"},
            ),
            ToolSpec(
                algorithm_id="algo.preprocess.building.source_normalize.v1",
                input_types=("dt.building.source_set", "dt.building.bundle"),
                output_type="dt.building.normalized_set",
                handler_name="_handle_building_source_normalize",
            ),
            ToolSpec(
                algorithm_id="algo.enrich.building.obm_attributes.v1",
                input_types=("dt.building.normalized_set",),
                output_type="dt.building.normalized_set",
                handler_name="_handle_building_obm_attributes",
            ),
            ToolSpec(
                algorithm_id="algo.validate.building.presence_raster.v1",
                input_types=("dt.building.normalized_set", "dt.raster.building_presence"),
                output_type="dt.building.presence_validated_set",
                handler_name="_handle_building_presence_raster",
            ),
            ToolSpec(
                algorithm_id="algo.match.building.v8_candidate_graph.v1",
                input_types=("dt.building.presence_validated_set", "dt.building.normalized_set"),
                output_type="dt.building.match_candidate_graph",
                handler_name="_handle_building_v8_candidate_graph",
            ),
            ToolSpec(
                algorithm_id="algo.match.building.v8_component_solver.v1",
                input_types=("dt.building.match_candidate_graph",),
                output_type="dt.building.match_components",
                handler_name="_handle_building_v8_component_solver",
            ),
            ToolSpec(
                algorithm_id="algo.fusion.building.cascade_geometry_priority.v1",
                input_types=("dt.building.match_components", "dt.building.normalized_set"),
                output_type="dt.building.fused_raw",
                handler_name="_handle_building_cascade_fusion",
            ),
            ToolSpec(
                algorithm_id="algo.resolve.building.residual_priority.v1",
                input_types=("dt.building.fused_raw",),
                output_type="dt.building.fused_raw",
                handler_name="_handle_building_residual_priority",
            ),
            ToolSpec(
                algorithm_id="algo.optimize.road.topology_for_buildings.v1",
                input_types=("dt.building.fused_raw", "dt.road.network"),
                output_type="dt.building.road_topology_adjusted",
                handler_name="_handle_building_road_topology",
            ),
            ToolSpec(
                algorithm_id="algo.optimize.building.conflict_graph.v1",
                input_types=("dt.building.road_topology_adjusted", "dt.building.fused_raw"),
                output_type="dt.building.conflict_optimized",
                handler_name="_handle_building_conflict_graph",
            ),
            ToolSpec(
                algorithm_id="algo.refine.building.post_conflict_shrink.v1",
                input_types=("dt.building.conflict_optimized",),
                output_type="dt.building.conflict_optimized",
                handler_name="_handle_building_post_conflict_shrink",
            ),
            ToolSpec(
                algorithm_id="algo.refine.building.road_tail.v1",
                input_types=("dt.building.conflict_optimized", "dt.road.network"),
                output_type="dt.building.conflict_optimized",
                handler_name="_handle_building_road_tail",
            ),
            ToolSpec(
                algorithm_id="algo.enrich.building.height_from_raster.v1",
                input_types=("dt.building.conflict_optimized", "dt.raster.building_height"),
                output_type="dt.building.height_enriched",
                handler_name="_handle_building_height_from_raster",
            ),
            ToolSpec(
                algorithm_id="algo.assess.building.quality_metrics.v1",
                input_types=("dt.building.height_enriched", "dt.building.conflict_optimized"),
                output_type="dt.building.quality_report",
                handler_name="_handle_building_quality_metrics",
            ),
            ToolSpec(
                algorithm_id="algo.fusion.building.multi_source.decomposed.v1",
                input_types=("dt.building.source_set", "dt.building.bundle"),
                output_type="dt.building.fused",
                handler_name="_handle_building_multi_source_decomposed",
                timeout_seconds=1800,
            ),
            ToolSpec(
                algorithm_id="algo.fusion.road.segment_match_topology.v1",
                input_types=("dt.road.bundle",),
                output_type="dt.road.fused",
                handler_name="_handle_road_segment_match_topology",
            ),
            ToolSpec(
                algorithm_id="algo.fusion.water.line_three_source_priority.v1",
                input_types=("dt.water.line_bundle",),
                output_type="dt.water.line_fused",
                handler_name="_handle_water_line_three_source",
            ),
            ToolSpec(
                algorithm_id="algo.fusion.water.polygon_priority_merge.v1",
                input_types=("dt.water.bundle",),
                output_type="dt.water.fused",
                handler_name="_handle_water_polygon_priority_merge",
            ),
            ToolSpec(
                algorithm_id="algo.fusion.poi.geohash_neighbor_match.v1",
                input_types=("dt.poi.bundle",),
                output_type="dt.poi.fused",
                handler_name="_handle_poi_geohash_neighbor_match",
            ),
            ToolSpec(
                algorithm_id="algo.detect.spatial_conflicts.v1",
                input_types=("dt.building.fused", "dt.water.fused", "dt.road.fused"),
                output_type="dt.building.quality_report",
                handler_name="_handle_spatial_conflicts",
            ),
        ]
    )
