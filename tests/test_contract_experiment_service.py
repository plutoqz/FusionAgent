from __future__ import annotations

import json
from pathlib import Path

from schemas.contract_experiment import ContractExperimentCase, ExperimentStageDeclaration
from schemas.scenario import ScenarioRunRequest
from services.contract_experiment_service import evaluate_case_contract


def _write_summary(path: Path, payload: dict) -> str:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _case(*, case_id: str, stages: list[ExperimentStageDeclaration], expected_gap_types: list[str]) -> ContractExperimentCase:
    return ContractExperimentCase(
        case_id=case_id,
        scenario_name=case_id,
        description="contract test",
        request=ScenarioRunRequest(
            trigger_content="contract test",
            metadata={"deferred_task_kinds": ["building"]},
        ),
        stages=stages,
        expected_layer_priority=["water_polygon"],
        expected_delivery_strategy="test",
        expected_gap_types=expected_gap_types,
    )


def test_c04_contract_requires_provisional_stage_and_supersession(tmp_path: Path) -> None:
    case = _case(
        case_id="C04",
        expected_gap_types=["source_unavailable"],
        stages=[
            ExperimentStageDeclaration(
                stage_id="initial",
                action="create",
                expected_phases=["partial_provisional"],
                expected_task_order=["water_polygon"],
                assertions={"provisional_required": True},
            ),
            ExperimentStageDeclaration(
                stage_id="resume",
                action="resume",
                expected_phases=["succeeded"],
                expected_task_order=["water_polygon"],
                assertions={"supersede_required": True},
            ),
        ],
    )
    initial_path = _write_summary(
        tmp_path / "initial.json",
        {
            "phase": "partial_provisional",
            "mission": {"task_kinds": ["water_polygon"]},
            "child_runs": [
                {
                    "task_kind": "water_polygon",
                    "phase": "succeeded",
                    "provisional": True,
                    "degradation": {
                        "state": "degraded",
                        "degraded_component_source_ids": ["raw.hydrolakes.water"],
                    },
                }
            ],
            "quality": {"accepted_child_count": 1, "rejected_child_count": 0},
        },
    )
    resume_path = _write_summary(
        tmp_path / "resume.json",
        {
            "phase": "succeeded",
            "mission": {"task_kinds": ["water_polygon"]},
            "child_runs": [
                {
                    "task_kind": "water_polygon",
                    "phase": "succeeded",
                    "degradation": {"state": "none", "degraded_component_source_ids": []},
                    "supersedes": "provisional-output",
                }
            ],
            "superseded_outputs": ["provisional-output"],
            "quality": {"accepted_child_count": 1, "rejected_child_count": 0},
        },
    )

    result = evaluate_case_contract(
        case=case,
        stage_records=[
            {"stage_id": "initial", "summary_path": initial_path},
            {"stage_id": "resume", "summary_path": resume_path},
        ],
        experiment_dir=tmp_path,
    )

    assert result["passed"] is True
    assert result["stage_evaluations"][0]["declared_assertions"]["provisional_required"] is True
    assert result["stage_evaluations"][1]["declared_assertions"]["supersede_required"] is True


def test_c06_contract_requires_full_failure_and_degraded_retry(tmp_path: Path) -> None:
    case = _case(
        case_id="C06",
        expected_gap_types=["quality_failed", "source_unavailable"],
        stages=[
            ExperimentStageDeclaration(
                stage_id="full",
                action="create",
                expected_phases=["failed"],
                expected_task_order=["road"],
                assertions={"quality_failure_required": True},
            ),
            ExperimentStageDeclaration(
                stage_id="retry",
                action="resume",
                expected_phases=["partial_provisional"],
                expected_task_order=["road"],
                assertions={"degraded_success_required": True},
            ),
        ],
    )
    full_path = _write_summary(
        tmp_path / "full.json",
        {
            "phase": "failed",
            "mission": {"task_kinds": ["road"]},
            "child_runs": [{"task_kind": "road", "phase": "failed", "error": "quality gate rejected"}],
            "quality": {"accepted_child_count": 0, "rejected_child_count": 1},
        },
    )
    retry_path = _write_summary(
        tmp_path / "retry.json",
        {
            "phase": "partial_provisional",
            "mission": {"task_kinds": ["road"]},
            "child_runs": [
                {
                    "task_kind": "road",
                    "phase": "partial_provisional",
                    "provisional": True,
                    "degradation": {
                        "state": "degraded",
                        "degraded_component_source_ids": ["raw.microsoft.road"],
                    },
                }
            ],
            "quality": {
                "accepted_child_count": 1,
                "rejected_child_count": 0,
                "child_reports": [{"accepted": True, "degraded_mode": True}],
            },
        },
    )

    result = evaluate_case_contract(
        case=case,
        stage_records=[
            {"stage_id": "full", "summary_path": full_path},
            {"stage_id": "retry", "summary_path": retry_path},
        ],
        experiment_dir=tmp_path,
    )

    assert result["passed"] is True
    assert result["assertions"]["quality_failure_observed"] is True
    assert result["assertions"]["degraded_or_provisional_observed"] is True
