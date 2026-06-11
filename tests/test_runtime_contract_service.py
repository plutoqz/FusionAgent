from __future__ import annotations

from agent.tooling import build_default_tool_registry
from kg.inmemory_repository import InMemoryKGRepository
from kg.models import AlgorithmNode, PatternStep, WorkflowPatternNode
from schemas.fusion import JobType
from services.runtime_contract_service import RuntimeContractService


def test_runtime_contract_allows_registered_runtime_candidate_algorithm() -> None:
    service = RuntimeContractService(InMemoryKGRepository(), tool_registry=build_default_tool_registry())

    decision = service.evaluate_algorithm("algo.fusion.road.conflation.v7", surface="validator")

    assert decision.allowed is True
    assert decision.reason_code is None
    assert decision.gap_severity == "none"
    assert decision.runtime_status == "runtime_candidate"


def test_runtime_contract_blocks_deprecated_algorithm_even_when_present_in_kg() -> None:
    service = RuntimeContractService(InMemoryKGRepository(), tool_registry=build_default_tool_registry())

    decision = service.evaluate_algorithm("algo.fusion.road.v1", surface="planner_fallback")

    assert decision.allowed is False
    assert decision.reason_code == "DEPRECATED_ALGORITHM"
    assert decision.gap_severity == "fail_soft"
    assert "deprecated_by" in decision.evidence


def test_runtime_contract_blocks_registry_missing_algorithm() -> None:
    repo = InMemoryKGRepository()
    algorithms = dict(repo.algorithms)
    algorithms["algo.fusion.custom.unregistered"] = AlgorithmNode(
        algo_id="algo.fusion.custom.unregistered",
        algo_name="Custom Unregistered",
        input_types=["dt.building.bundle"],
        output_type="dt.building.fused",
        task_type="building_fusion",
        tool_ref="custom:missing",
        metadata={"runtime_status": "runtime_candidate", "selectable_now": True},
    )
    service = RuntimeContractService(
        InMemoryKGRepository(algorithms=algorithms),
        tool_registry=build_default_tool_registry(),
    )

    decision = service.evaluate_algorithm("algo.fusion.custom.unregistered", surface="executor")

    assert decision.allowed is False
    assert decision.reason_code == "UNKNOWN_TOOL"
    assert decision.gap_severity == "unguarded"


def test_runtime_contract_blocks_pattern_containing_deprecated_step() -> None:
    repo = InMemoryKGRepository()
    algorithms = dict(repo.algorithms)
    algorithms["algo.test.deprecated.injected"] = AlgorithmNode(
        algo_id="algo.test.deprecated.injected",
        algo_name="Injected Deprecated Algorithm",
        input_types=["dt.road.bundle"],
        output_type="dt.road.fused",
        task_type="road_fusion",
        tool_ref="test:deprecated",
        usage_mode="deprecated",
        metadata={
            "runtime_status": "deprecated",
            "selectable_now": False,
            "deprecated_by": "algo.fusion.road.conflation.v7",
        },
    )
    repo = InMemoryKGRepository(algorithms=algorithms)
    pattern = WorkflowPatternNode(
        pattern_id="wp.bad.deprecated",
        pattern_name="Bad Deprecated Pattern",
        job_type=JobType.road,
        disaster_types=["generic"],
        steps=[
            PatternStep(
                order=1,
                name="deprecated_road",
                algorithm_id="algo.test.deprecated.injected",
                input_data_type="dt.road.bundle",
                output_data_type="dt.road.fused",
                data_source_id="catalog.flood.road",
            )
        ],
    )
    service = RuntimeContractService(repo, tool_registry=build_default_tool_registry())

    decision = service.evaluate_pattern(pattern, surface="planner_fallback")

    assert decision.allowed is False
    assert decision.reason_code == "PATTERN_CONTAINS_BLOCKED_ALGORITHM"
    assert decision.evidence["blocked_algorithm_ids"] == ["algo.test.deprecated.injected"]


def test_runtime_contract_filters_alternatives_and_reports_skips() -> None:
    repo = InMemoryKGRepository()
    algorithms = dict(repo.algorithms)
    building_safe = algorithms["algo.fusion.building.safe"]
    algorithms["algo.fusion.building.safe"] = AlgorithmNode(
        algo_id=building_safe.algo_id,
        algo_name=building_safe.algo_name,
        input_types=building_safe.input_types,
        output_type=building_safe.output_type,
        task_type=building_safe.task_type,
        tool_ref=building_safe.tool_ref,
        success_rate=building_safe.success_rate,
        accuracy_score=building_safe.accuracy_score,
        stability_score=building_safe.stability_score,
        usage_mode=building_safe.usage_mode,
        metadata={**building_safe.metadata, "runtime_status": "runtime_candidate", "selectable_now": True},
        alternatives=building_safe.alternatives,
    )
    service = RuntimeContractService(
        InMemoryKGRepository(algorithms=algorithms),
        tool_registry=build_default_tool_registry(),
    )

    result = service.filter_algorithm_ids(
        ["algo.fusion.building.safe", "algo.fusion.road.v1", "algo.fusion.unknown"],
        surface="executor_healing",
    )

    assert result.allowed_ids == ["algo.fusion.building.safe"]
    assert [item["algorithm_id"] for item in result.skipped] == [
        "algo.fusion.road.v1",
        "algo.fusion.unknown",
    ]
    assert result.skipped[0]["reason_code"] == "DEPRECATED_ALGORITHM"
    assert result.skipped[1]["reason_code"] == "UNKNOWN_ALGORITHM"
