from __future__ import annotations

from pathlib import Path
from typing import Any

from schemas.agent import RepairRecord, RunCreateRequest, WorkflowPlan
from services.aoi_resolution_service import ResolvedAOI
from services.input_acquisition_service import ResolvedRunInputs


class RunExecutionRouter:
    def __init__(self, coordinator: Any) -> None:
        self.coordinator = coordinator

    def run_selected_execution_stage(
        self,
        *,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        osm_zip_path: Path,
        ref_zip_path: Path,
        intermediate_dir: Path,
        output_dir: Path,
        repair_records: list[RepairRecord],
        runtime_dependencies: Any,
        resolved_inputs: ResolvedRunInputs | None,
        resolved_aoi: ResolvedAOI | None,
        multisource_building_sources: tuple[dict[str, Path], dict[str, Path]] | None,
        should_tile: bool,
        should_use_large_area_runtime: bool,
    ) -> tuple[Path, list[RepairRecord]]:
        service = self.coordinator
        if (
            multisource_building_sources is not None
            and service._should_use_multisource_building_runtime(request, plan)
            and len(multisource_building_sources[0]) >= 2
        ):
            return service.run_multisource_building_execution_stage(
                run_id=run_id,
                request=request,
                plan=plan,
                intermediate_dir=intermediate_dir,
                output_dir=output_dir,
                vector_sources=multisource_building_sources[0],
                raster_sources=multisource_building_sources[1],
                resolved_aoi=resolved_aoi,
                repair_records=repair_records,
            )
        if should_tile:
            return service.run_tiled_execution_stage(
                run_id=run_id,
                request=request,
                plan=plan,
                osm_zip_path=osm_zip_path,
                ref_zip_path=ref_zip_path,
                intermediate_dir=intermediate_dir,
                output_dir=output_dir,
                repair_records=repair_records,
                resolved_inputs=resolved_inputs,
                resolved_aoi=resolved_aoi,
            )
        if should_use_large_area_runtime and resolved_inputs is not None:
            return service.run_large_area_execution_stage(
                run_id=run_id,
                request=request,
                plan=plan,
                intermediate_dir=intermediate_dir,
                output_dir=output_dir,
                resolved_inputs=resolved_inputs,
                resolved_aoi=resolved_aoi,
                repair_records=repair_records,
            )
        return service.run_execution_stage(
            run_id=run_id,
            request=request,
            plan=plan,
            osm_zip_path=osm_zip_path,
            ref_zip_path=ref_zip_path,
            intermediate_dir=intermediate_dir,
            output_dir=output_dir,
            repair_records=repair_records,
            runtime_dependencies=runtime_dependencies,
        )
