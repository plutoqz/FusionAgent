from pathlib import Path

from agent.executor import ExecutionContext, WorkflowExecutor
from kg.inmemory_repository import InMemoryKGRepository
from schemas.agent import RunTrigger, RunTriggerType, WorkflowPlan, WorkflowTask, WorkflowTaskInput, WorkflowTaskOutput
from schemas.fusion import JobType


def test_executor_records_reason_codes_for_healing_attempts(tmp_path: Path) -> None:
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
        workflow_id="wf_repair_audit",
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
    repairs = []
    artifact = executor.execute_plan(plan=plan, context=ctx, repair_records=repairs)

    assert artifact == output_file
    assert repairs[0].reason_code == "primary_execution_failed"
    assert repairs[-1].reason_code == "alternative_algorithm_succeeded"


def test_executor_skips_deprecated_healing_alternative_with_decision_evidence(tmp_path: Path) -> None:
    output_file = tmp_path / "ok.shp"
    output_file.write_text("dummy", encoding="utf-8")

    def fail_handler(_ctx: ExecutionContext) -> Path:
        raise RuntimeError("primary failed")

    def ok_handler(_ctx: ExecutionContext) -> Path:
        return output_file

    executor = WorkflowExecutor(
        kg_repo=InMemoryKGRepository(),
        algorithm_handlers={
            "algo.fusion.road.conflation.v7": fail_handler,
            "algo.fusion.building.safe": ok_handler,
        },
    )
    plan = WorkflowPlan(
        workflow_id="wf_repair_audit_contract",
        trigger=RunTrigger(type=RunTriggerType.user_query, content="repair"),
        context={},
        tasks=[
            WorkflowTask(
                step=1,
                name="road_fusion",
                description="road fusion",
                algorithm_id="algo.fusion.road.conflation.v7",
                input=WorkflowTaskInput(
                    data_type_id="dt.road.bundle",
                    data_source_id="catalog.flood.road",
                    parameters={},
                ),
                output=WorkflowTaskOutput(data_type_id="dt.road.fused", description=""),
                alternatives=["algo.fusion.road.v1", "algo.fusion.building.safe"],
                kg_validated=True,
            )
        ],
        expected_output="road",
    )
    ctx = ExecutionContext(
        run_id="r1",
        job_type=JobType.road,
        osm_shp=tmp_path / "osm.shp",
        ref_shp=tmp_path / "ref.shp",
        output_dir=tmp_path,
        target_crs="EPSG:4326",
    )
    repairs = []

    artifact = executor.execute_plan(plan=plan, context=ctx, repair_records=repairs)

    assert artifact == output_file
    success = next(record for record in repairs if record.reason_code == "alternative_algorithm_succeeded")
    assert success.policy_source == "runtime_contract"
    assert [item["algorithm_id"] for item in success.candidate_actions] == [
        "algo.fusion.road.v1",
        "algo.fusion.building.safe",
    ]
    assert success.selected_action["algorithm_id"] == "algo.fusion.building.safe"
    assert success.skipped_actions[0]["algorithm_id"] == "algo.fusion.road.v1"
    assert success.skipped_actions[0]["reason_code"] == "DEPRECATED_ALGORITHM"
