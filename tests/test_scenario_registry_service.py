from __future__ import annotations

import json
from pathlib import Path

from services.scenario_registry_service import ScenarioRegistryService


def test_scenario_registry_records_jsonl_and_loads_summary(tmp_path: Path):
    service = ScenarioRegistryService(output_root=tmp_path)
    scenario_dir = tmp_path / "scenario-a"
    scenario_dir.mkdir()
    (scenario_dir / "scenario_summary.json").write_text(
        json.dumps({"scenario_id": "scenario-a", "scenario_name": "Parakou earthquake"}),
        encoding="utf-8",
    )

    service.record(
        {
            "scenario_id": "scenario-a",
            "scenario_name": "Parakou earthquake",
            "phase": "succeeded",
            "output_dir": str(scenario_dir),
            "child_run_ids": ["run-building", "run-road"],
            "created_at": "2026-04-21T00:00:00+00:00",
            "case_id": "parakou_earthquake_building_road",
        }
    )

    records = service.list_records()
    summary = service.get_summary("scenario-a")

    assert records[0]["scenario_id"] == "scenario-a"
    assert records[0]["phase"] == "succeeded"
    assert summary["scenario_name"] == "Parakou earthquake"


def test_scenario_registry_filters_records_by_phase(tmp_path: Path):
    service = ScenarioRegistryService(output_root=tmp_path)

    service.record({"scenario_id": "scenario-a", "phase": "succeeded"})
    service.record({"scenario_id": "scenario-b", "phase": "partial"})

    records = service.list_records(phase="succeeded")

    assert [record["scenario_id"] for record in records] == ["scenario-a"]


def test_scenario_registry_lists_most_recent_records_first(tmp_path: Path):
    service = ScenarioRegistryService(output_root=tmp_path)

    service.record({"scenario_id": "scenario-old", "phase": "succeeded"})
    service.record({"scenario_id": "scenario-new", "phase": "succeeded"})

    records = service.list_records(limit=10)

    assert [record["scenario_id"] for record in records] == [
        "scenario-new",
        "scenario-old",
    ]


def test_scenario_registry_applies_recent_first_with_phase_filter_and_limit(
    tmp_path: Path,
):
    service = ScenarioRegistryService(output_root=tmp_path)

    service.record({"scenario_id": "scenario-1", "phase": "partial"})
    service.record({"scenario_id": "scenario-2", "phase": "succeeded"})
    service.record({"scenario_id": "scenario-3", "phase": "partial"})
    service.record({"scenario_id": "scenario-4", "phase": "succeeded"})
    service.record({"scenario_id": "scenario-5", "phase": "partial"})

    records = service.list_records(limit=2, phase="partial")

    assert [record["scenario_id"] for record in records] == [
        "scenario-5",
        "scenario-3",
    ]
