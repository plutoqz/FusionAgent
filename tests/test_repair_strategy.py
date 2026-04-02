from pathlib import Path

from agent.executor import ExecutionContext, WorkflowExecutor
from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import (
    RepairRecord,
    RunTrigger,
    RunTriggerType,
    WorkflowPlan,
    WorkflowTask,
    WorkflowTaskInput,
    WorkflowTaskOutput,
)
from schemas.fusion import JobType


def test_executor_uses_alternative_algorithm(tmp_path: Path) -> None:
    output_file = tmp_path / "ok.shp"
    output_file.write_text("dummy", encoding="utf-8")

    def fail_handler(_ctx: ExecutionContext) -> Path:
        raise RuntimeError("primary failed")

    def ok_handler(_ctx: ExecutionContext) -> Path:
        return output_file

    executor = WorkflowExecutor(
        kg_repo=InMemoryKGRepository(),
        algorithm_handlers={
            "algo.fusion.building.v1": fail_handler,
            "algo.fusion.building.safe": ok_handler,
        },
    )

    plan = WorkflowPlan(
        workflow_id="wf_repair",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="repair"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="building_fusion",
                description="building fusion",
                algorithm_id="algo.fusion.building.v1",
                input=WorkflowTaskInput(data_type_id="dt.building.bundle", data_source_id="upload.bundle", parameters={}),
                output=WorkflowTaskOutput(data_type_id="dt.building.fused", description=""),
                depends_on=[],
                is_transform=False,
                kg_validated=True,
                alternatives=["algo.fusion.building.safe"],
            )
        ],
        expected_output="building result",
    )

    ctx = ExecutionContext(
        run_id="r1",
        job_type=JobType.building,
        osm_shp=tmp_path / "osm.shp",
        ref_shp=tmp_path / "ref.shp",
        output_dir=tmp_path,
        target_crs="EPSG:4326",
    )
    repairs: list[RepairRecord] = []
    artifact = executor.execute_plan(plan=plan, context=ctx, repair_records=repairs)

    assert artifact == output_file
    assert any(r.strategy == "alternative_algorithm" and r.success for r in repairs)

