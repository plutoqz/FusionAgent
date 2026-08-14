from copy import deepcopy
from pathlib import Path

import pytest

from scripts.run_p4_c04_road_e2e import _evaluate_stages, preflight_p4_c04_runner


FREEZE_V1 = (
    Path(__file__).parents[1]
    / "docs"
    / "current"
    / "evidence"
    / "p4-planning-e2e"
    / "2026-08-14-c04-road-protocol-freeze-v1"
)


def test_v1_freeze_remains_execution_blocked() -> None:
    report = preflight_p4_c04_runner(FREEZE_V1)

    assert report["passed"] is False
    assert report["checks"]["execution_ready"] is False
    assert report["fusion_runs_started"] == 0


def test_stage_evaluation_requires_new_artifact_and_exact_plan() -> None:
    first, second = _valid_stage_records()

    evaluation = _evaluate_stages([first, second])

    assert evaluation["passed"] is True
    assert evaluation["evaluated"]["supersession"]["verified"] is True


@pytest.mark.parametrize(
    ("mutation", "failed_check"),
    [
        (lambda first, second: first["component_coverage"]["raw.osm.road"].update(feature_count=0), "provisional_osm_materialized_non_empty"),
        (lambda first, second: first["component_coverage"]["raw.microsoft.road"].update(feature_count=1, path="ms.shp"), "provisional_microsoft_not_materialized"),
        (lambda first, second: second["component_coverage"]["raw.microsoft.road"].update(feature_count=0, path=None), "arrival_osm_and_microsoft_materialized_non_empty"),
        (lambda first, second: second["quality_evaluation"].update(event_count=0), "quality_evaluated_each_stage"),
        (lambda first, second: second.update(artifact_sha256="artifact-1"), "new_artifact_observed"),
        (lambda first, second: second.update(run_id="run-1"), "independent_runtime_runs"),
    ],
)
def test_stage_evaluation_fails_closed_when_evidence_is_missing(mutation, failed_check) -> None:
    first, second = _valid_stage_records()
    mutation(first, second)

    evaluation = _evaluate_stages([first, second])

    assert evaluation["passed"] is False
    assert evaluation["checks"][failed_check] is False
    assert evaluation["checks"]["supersession_evidence_complete"] is False


def _valid_stage_records() -> tuple[dict, dict]:
    base = {
        "runtime_succeeded": True,
        "injected_plan_sha256": "sha256:plan",
        "expected_plan_sha256": "sha256:plan",
        "frozen_plan_injected_event_count": 1,
        "selected_delivery_state": "degraded",
    }
    first = {
        **deepcopy(base),
        "stage_id": "osm_provisional",
        "run_id": "run-1",
        "artifact_sha256": "artifact-1",
        "prepared_inputs": {"active_source_ids": ["raw.osm.road", "aoi.venezuela_capital_district"]},
        "component_coverage": {
            "raw.osm.road": {"feature_count": 7, "coverage_status": "available", "path": "osm.shp"},
            "raw.microsoft.road": {"feature_count": 0, "coverage_status": "missing", "path": None},
        },
        "provisional_evidence": {"declared_delayed_source_ids": ["raw.microsoft.road"]},
        "quality_evaluation": {
            "event_count": 1,
            "accepted": True,
            "report_path": "quality-1.json",
            "report_sha256": "quality-1",
            "component_coverage": None,
        },
    }
    second = {
        **deepcopy(base),
        "stage_id": "microsoft_arrival",
        "run_id": "run-2",
        "artifact_sha256": "artifact-2",
        "prepared_inputs": {
            "active_source_ids": [
                "raw.osm.road",
                "raw.microsoft.road",
                "aoi.venezuela_capital_district",
            ]
        },
        "component_coverage": {
            "raw.osm.road": {"feature_count": 7, "coverage_status": "available", "path": "osm.shp"},
            "raw.microsoft.road": {"feature_count": 5, "coverage_status": "available", "path": "ms.shp"},
        },
        "provisional_evidence": {"declared_delayed_source_ids": []},
        "quality_evaluation": {
            "event_count": 1,
            "accepted": True,
            "report_path": "quality-2.json",
            "report_sha256": "quality-2",
            "component_coverage": None,
        },
    }
    for record in (first, second):
        coverage = deepcopy(record["component_coverage"])
        record["source_materialization"] = {
            "sha256": f"manifest-{record['run_id']}",
            "manifest": {"component_coverage": coverage},
        }
        record["quality_evaluation"]["component_coverage"] = deepcopy(coverage)
    return first, second
