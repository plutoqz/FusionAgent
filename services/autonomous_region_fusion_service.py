from __future__ import annotations

from pathlib import Path
from typing import Protocol

from schemas.fusion import JobType
from schemas.scenario import ScenarioRunRequest, ScenarioRunResponse
from schemas.task_kind import FULL_DISASTER_TASK_KINDS, TaskKind, task_kind_to_job_type


class _ScenarioRunService(Protocol):
    def create_scenario_run(self, request: ScenarioRunRequest) -> ScenarioRunResponse:
        ...


class AutonomousRegionFusionService:
    def __init__(self, *, scenario_run_service: _ScenarioRunService) -> None:
        self.scenario_run_service = scenario_run_service

    def run_autonomous_fusion_region(
        self,
        *,
        region_name: str,
        output_dir: Path,
        task_kinds: list[TaskKind] | None = None,
        degradation_policy: str = "evidence_preserving",
    ) -> ScenarioRunResponse:
        if task_kinds is not None and not task_kinds:
            raise ValueError("task_kinds must include at least one task kind")

        selected_task_kinds = list(task_kinds if task_kinds is not None else FULL_DISASTER_TASK_KINDS)
        job_types = _job_types_for_task_kinds(selected_task_kinds)
        request = ScenarioRunRequest(
            scenario_name=f"Autonomous fusion for {region_name}",
            trigger_content=(
                f"Autonomously fuse requested geospatial themes for {region_name}. "
                "Resolve the AOI and acquire all required public sources automatically."
            ),
            disaster_type="generic",
            job_types=job_types,
            spatial_extent=region_name,
            force_aoi_resolution=True,
            output_root=str(Path(output_dir)),
            metadata={
                "requested_task_kinds": [task_kind.value for task_kind in selected_task_kinds],
                "degradation_policy": degradation_policy,
                "entrypoint": "run_autonomous_fusion_region",
            },
        )
        return self.scenario_run_service.create_scenario_run(request)


def _job_types_for_task_kinds(task_kinds: list[TaskKind]) -> list[JobType]:
    ordered: list[JobType] = []
    for task_kind in task_kinds:
        job_type = task_kind_to_job_type(task_kind)
        if job_type not in ordered:
            ordered.append(job_type)
    return ordered
