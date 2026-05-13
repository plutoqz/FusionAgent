from __future__ import annotations

import pytest

from schemas.agent import RepairRecord
from services.agent_run_service import AgentRunService
from schemas.failure_taxonomy import classify_failure_category, classify_failure_details


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("missing source bundle for catalog.flood.building", "SOURCE_MISSING"),
        ("corrupted shapefile header", "SOURCE_CORRUPTED"),
        ("CRS mismatch between EPSG:4326 and EPSG:32631", "CRS_MISMATCH"),
        ("PARAM_OUT_OF_RANGE", "PARAM_OUT_OF_RANGE"),
        ("TimeoutError: algorithm execution timed out after 30s", "ALGO_TIMEOUT"),
        ("suspect output: semantically empty geometry collection", "SUSPECT_OUTPUT"),
        ("RuntimeError: primary execution failed", "ALGO_RUNTIME_ERROR"),
    ],
)
def test_failures_map_to_machine_readable_categories(raw: str, expected: str) -> None:
    assert classify_failure_category(raw) == expected


def test_classify_failure_details_preserves_root_cause_and_operator_guidance() -> None:
    details = classify_failure_details(
        error="RuntimeError: primary failed",
        reason_code="primary_execution_failed",
    )

    assert details.model_dump(mode="json") == {
        "failure_category": "ALGO_RUNTIME_ERROR",
        "root_cause": "PRIMARY_EXECUTION_FAILED",
        "recoverable": True,
        "suggested_action": "replan",
    }


def test_step_failure_operator_note_includes_failure_taxonomy_fields() -> None:
    repair_records = [
        RepairRecord(
            attempt_no=1,
            strategy="alternative_source",
            step=1,
            message="Primary execution failed: source missing",
            success=False,
            timestamp="2026-05-13T00:00:00+00:00",
            reason_code="primary_execution_failed",
        )
    ]

    note = AgentRunService._build_step_failure_operator_note(repair_records=repair_records, current_step=1)

    assert note == {
        "root_cause": "PRIMARY_EXECUTION_FAILED",
        "failure_category": "ALGO_RUNTIME_ERROR",
        "action": "replan",
        "recoverable": True,
        "suggested_action": "replan",
    }


def test_failure_summary_includes_failure_taxonomy_hint() -> None:
    repair_records = [
        RepairRecord(
            attempt_no=1,
            strategy="alternative_source",
            step=1,
            message="Primary execution failed: source missing",
            success=False,
            timestamp="2026-05-13T00:00:00+00:00",
            reason_code="primary_execution_failed",
        )
    ]

    summary = AgentRunService._build_failure_summary("RuntimeError: primary failed", repair_records)

    assert "failure_category=ALGO_RUNTIME_ERROR" in summary
    assert "suggested_action=replan" in summary
