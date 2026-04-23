from pathlib import Path

import pytest

from agent.executor import ExecutionContext, WorkflowExecutor
from agent.tooling import ToolRegistry, ToolSpec, build_default_tool_registry
from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import RunTrigger, RunTriggerType, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from schemas.fusion import JobType


def _build_context(tmp_path: Path) -> ExecutionContext:
    osm_shp = tmp_path / "osm.shp"
    ref_shp = tmp_path / "ref.shp"
    osm_shp.write_text("", encoding="utf-8")
    ref_shp.write_text("", encoding="utf-8")
    return ExecutionContext(
        run_id="run-tool-registry",
        job_type=JobType.building,
        osm_shp=osm_shp,
        ref_shp=ref_shp,
        output_dir=tmp_path,
        target_crs="EPSG:4326",
    )


def test_build_default_tool_registry_exposes_expected_fusion_specs() -> None:
    registry = build_default_tool_registry()

    expected_specs = {
        "algo.fusion.building.v1": (("dt.building.bundle",), "dt.building.fused", "_handle_building"),
        "algo.fusion.building.safe": (("dt.building.bundle",), "dt.building.fused", "_handle_building_safe"),
        "algo.fusion.road.v1": (("dt.road.bundle",), "dt.road.fused", "_handle_road"),
        "algo.fusion.road.safe": (("dt.road.bundle",), "dt.road.fused", "_handle_road"),
        "algo.fusion.water.v1": (("dt.water.bundle",), "dt.water.fused", "_handle_water"),
        "algo.fusion.poi.v1": (("dt.poi.bundle",), "dt.poi.fused", "_handle_poi"),
    }

    for algorithm_id, (input_types, output_type, handler_name) in expected_specs.items():
        spec = registry.require(algorithm_id)
        assert spec.input_types == input_types
        assert spec.output_type == output_type
        assert spec.handler_name == handler_name
        assert spec.timeout_seconds == 600
        assert spec.error_policy["missing_handler"] == "fail_closed"

    reserved = registry.require("algo.transform.trajectory_to_road_candidate")
    assert reserved.input_types == ("dt.trajectory.raw",)
    assert reserved.output_type == "dt.road.candidate"
    assert reserved.handler_name == "_handle_reserved_trajectory_pretransform"
    assert reserved.error_policy["missing_handler"] == "fail_closed"


def test_tool_registry_require_raises_clear_error_for_unknown_algorithm() -> None:
    registry = build_default_tool_registry()

    with pytest.raises(ValueError, match="Unknown algorithm.*algo\\.fusion\\.unknown\\.v1"):
        registry.require("algo.fusion.unknown.v1")


def test_execute_algorithm_fails_on_registry_miss_before_handler_lookup(tmp_path: Path) -> None:
    called = False

    def unexpected_handler(_context: ExecutionContext) -> Path:
        nonlocal called
        called = True
        return tmp_path / "unexpected.shp"

    registry = ToolRegistry(
        [
            ToolSpec(
                algorithm_id="algo.fusion.building.v1",
                input_types=("dt.building.bundle",),
                output_type="dt.building.fused",
                handler_name="_handle_building",
            )
        ]
    )
    executor = WorkflowExecutor(
        kg_repo=object(),
        algorithm_handlers={"algo.fusion.unknown.v1": unexpected_handler},
        tool_registry=registry,
    )

    with pytest.raises(ValueError, match="Unknown algorithm.*algo\\.fusion\\.unknown\\.v1"):
        executor._execute_algorithm("algo.fusion.unknown.v1", _build_context(tmp_path))

    assert called is False


def test_execute_algorithm_uses_custom_handler_for_registered_algorithm(tmp_path: Path) -> None:
    expected = tmp_path / "custom-output.shp"
    expected.write_text("ok", encoding="utf-8")

    def custom_handler(_context: ExecutionContext) -> Path:
        return expected

    executor = WorkflowExecutor(
        kg_repo=object(),
        algorithm_handlers={"algo.fusion.building.v1": custom_handler},
        tool_registry=build_default_tool_registry(),
    )

    result = executor._execute_algorithm("algo.fusion.building.v1", _build_context(tmp_path))

    assert result == expected


def test_execute_plan_does_not_reuse_previous_step_output_when_next_step_fails_registry_lookup(
    tmp_path: Path,
) -> None:
    first_step_output = tmp_path / "step-1-output.shp"
    first_step_output.write_text("step-1", encoding="utf-8")

    def building_handler(_context: ExecutionContext) -> Path:
        return first_step_output

    executor = WorkflowExecutor(
        kg_repo=InMemoryKGRepository(),
        algorithm_handlers={"algo.fusion.building.v1": building_handler},
        tool_registry=build_default_tool_registry(),
    )
    plan = WorkflowPlan(
        workflow_id="wf_registry_fail_closed",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="two-step registry failure"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="step 1 succeeds",
                algorithm_id="algo.fusion.building.v1",
                input=WorkflowTaskInput(
                    data_type_id="dt.building.bundle",
                    data_source_id="upload.bundle",
                    parameters={},
                ),
                output=WorkflowTaskOutput(data_type_id="dt.building.fused", description=""),
                depends_on=[],
                is_transform=False,
                kg_validated=True,
                alternatives=[],
            ),
            WorkflowTask(
                step=2,
                name="unknown_fusion",
                description="step 2 is not registered",
                algorithm_id="algo.fusion.unknown.v1",
                input=WorkflowTaskInput(
                    data_type_id="dt.building.bundle",
                    data_source_id="upload.bundle",
                    parameters={},
                ),
                output=WorkflowTaskOutput(data_type_id="dt.building.fused", description=""),
                depends_on=[1],
                is_transform=False,
                kg_validated=True,
                alternatives=[],
            ),
        ],
        expected_output="must fail closed on step 2",
    )

    repair_records = []

    with pytest.raises(RuntimeError, match="Task failed after healing strategies: step=2, algo=algo\\.fusion\\.unknown\\.v1"):
        executor.execute_plan(plan=plan, context=_build_context(tmp_path), repair_records=repair_records)

    assert any(record.step == 2 and record.reason_code == "primary_execution_failed" for record in repair_records)
    assert all(record.to_algorithm != "algo.fusion.building.v1" for record in repair_records)
