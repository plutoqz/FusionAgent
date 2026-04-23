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
        ]
    )
