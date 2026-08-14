from copy import deepcopy

from scripts.run_p4_c02_e2e import _evaluate_stages, _fusion_execution_counts


def test_c02_stage_evaluation_accepts_complete_three_stage_chain() -> None:
    records = _valid_stage_records()

    evaluation = _evaluate_stages(
        records=records,
        config=_config(),
        selected_hash="sha256:selected",
        resolved_hash="sha256:resolved",
    )

    assert evaluation["passed"] is True
    assert evaluation["selected"]["preserved"] is True
    assert evaluation["executed"]["run_ids"] == ["run-water_polygon", "run-waterways", "run-road"]


def test_c02_stage_evaluation_fails_when_semantic_contract_is_invalid() -> None:
    records = _valid_stage_records()
    records[1]["source_semantic_contract"]["contract"]["validation"]["valid"] = False

    evaluation = _evaluate_stages(
        records=records,
        config=_config(),
        selected_hash="sha256:selected",
        resolved_hash="sha256:resolved",
    )

    assert evaluation["passed"] is False
    assert evaluation["checks"]["semantic_contracts_valid"] is False


def test_c02_stage_evaluation_fails_when_gap_layer_is_executed() -> None:
    records = _valid_stage_records()
    records.append({"stage_id": "building", "task_kind": "building", "run_id": "run-building"})

    evaluation = _evaluate_stages(
        records=records,
        config=_config(),
        selected_hash="sha256:selected",
        resolved_hash="sha256:resolved",
    )

    assert evaluation["passed"] is False
    assert evaluation["checks"]["building_poi_gap_only"] is False


def test_c02_failure_counts_large_area_execution_events() -> None:
    assert _fusion_execution_counts(
        [{"events": [{"kind": "large_area_tile_started"}, {"kind": "large_area_tile_completed"}]}]
    ) == {
        "fusion_algorithm_executions_started": 1,
        "fusion_algorithm_executions_completed": 1,
    }


def _config() -> dict:
    stages = {
        "water_polygon": ["raw.osm.water", "raw.hydrolakes.water"],
        "waterways": ["raw.osm.waterways", "raw.hydrorivers.water"],
        "road": ["raw.osm.road", "raw.microsoft.road"],
    }
    return {
        "aoi": {"boundary_source_id": "aoi.venezuela_capital_district"},
        "stages": [
            {
                "stage_id": stage_id,
                "active_source_ids": source_ids + ["aoi.venezuela_capital_district"],
            }
            for stage_id, source_ids in stages.items()
        ],
        "gap_declaration": {
            "building": {"materialize": False, "reason_code": "DELIVERY_STATE_GAP", "status": "gap"},
            "poi": {"materialize": False, "reason_code": "DELIVERY_STATE_GAP", "status": "gap"},
        },
    }


def _valid_stage_records() -> list[dict]:
    sources = {
        "water_polygon": ["raw.osm.water", "raw.hydrolakes.water"],
        "waterways": ["raw.osm.waterways", "raw.hydrorivers.water"],
        "road": ["raw.osm.road", "raw.microsoft.road"],
    }
    records = []
    for stage_id, source_ids in sources.items():
        coverage = {
            source_id: {"feature_count": 3, "coverage_status": "available", "path": f"{source_id}.zip"}
            for source_id in source_ids
        }
        records.append(
            {
                "stage_id": stage_id,
                "task_kind": stage_id,
                "run_id": f"run-{stage_id}",
                "runtime_succeeded": True,
                "planning_telemetry": {
                    "planning_mode": "frozen_workflow_plan_injection",
                    "llm_calls": 0,
                },
                "injected_plan_sha256": f"sha256:{stage_id}",
                "expected_plan_sha256": f"sha256:{stage_id}",
                "frozen_plan_injected_event_count": 1,
                "component_coverage": coverage,
                "source_materialization": {
                    "sha256": f"manifest-{stage_id}",
                    "manifest": {"component_coverage": deepcopy(coverage)},
                },
                "source_semantic_contract": {
                    "sha256": f"contract-{stage_id}",
                    "contract": {
                        "component_source_ids": source_ids,
                        "validation": {"valid": True},
                    },
                },
                "quality_evaluation": {
                    "event_count": 1,
                    "accepted": True,
                    "report_path": f"quality-{stage_id}.json",
                    "report_sha256": f"quality-{stage_id}",
                    "component_coverage": deepcopy(coverage),
                },
                "artifact_sha256": f"artifact-{stage_id}",
                "output_artifacts": [{"suffix": ".gpkg", "sha256": f"gpkg-{stage_id}"}],
                "events": [{"kind": "frozen_plan_injected", "attempt_no": 0}],
                "prepared_inputs": {
                    "active_source_ids": source_ids + ["aoi.venezuela_capital_district"]
                },
            }
        )
    return records
