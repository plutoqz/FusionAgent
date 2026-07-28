from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import LineString, Polygon

from scripts.run_product_contract_experiment import (
    build_planning_context,
    build_planning_decision,
    build_product_contract,
    build_resource_regime,
    find_case,
    load_cases,
    run_product_contract_experiment,
)
from services.product_contract_runtime_service import (
    MaterializedRuntimeSource,
    ProductContractRuntimeExecutor,
)


class RecordingMaterializer:
    def __init__(self, *, fail_sources: set[str] | None = None) -> None:
        self.calls: list[str] = []
        self.fail_sources = set(fail_sources or set())

    def materialize(
        self,
        *,
        source_id: str,
        bbox: tuple[float, float, float, float],
        target_dir: Path,
        target_crs: str,
    ) -> MaterializedRuntimeSource:
        self.calls.append(source_id)
        if source_id in self.fail_sources:
            raise RuntimeError(f"forced materialization failure for {source_id}")
        target_dir.mkdir(parents=True, exist_ok=True)
        minx, miny, maxx, maxy = bbox
        if source_id in {"raw.osm.building", "raw.hydrolakes.water"}:
            geometry = Polygon(
                [
                    (minx + (maxx - minx) * 0.1, miny + (maxy - miny) * 0.1),
                    (maxx - (maxx - minx) * 0.1, miny + (maxy - miny) * 0.1),
                    (maxx - (maxx - minx) * 0.1, maxy - (maxy - miny) * 0.1),
                    (minx + (maxx - minx) * 0.1, maxy - (maxy - miny) * 0.1),
                ]
            )
        else:
            geometry = LineString(
                [
                    (minx + (maxx - minx) * 0.05, miny + (maxy - miny) * 0.05),
                    (maxx - (maxx - minx) * 0.05, maxy - (maxy - miny) * 0.05),
                ]
            )
        frame = gpd.GeoDataFrame(
            {
                "name": ["runtime road"],
                "road_class": ["primary"],
            },
            geometry=[geometry],
            crs="EPSG:4326",
        ).to_crs(target_crs)
        vector_path = target_dir / "source.gpkg"
        frame.to_file(vector_path, driver="GPKG")
        return MaterializedRuntimeSource(
            artifact_path=vector_path,
            vector_path=vector_path,
            feature_count=1,
            coverage_status="available",
            source_mode="test_real_vector",
        )


def _case(case_id: str) -> dict:
    return find_case(load_cases(), case_id)


def _fixed_decision(case: dict) -> dict:
    contract = build_product_contract(case)
    context = build_planning_context(
        case,
        contract,
        build_resource_regime(case),
        planner="fixed",
    )
    return build_planning_decision(case, "fixed", context)


def _executor(
    tmp_path: Path,
    materializer: RecordingMaterializer,
) -> ProductContractRuntimeExecutor:
    return ProductContractRuntimeExecutor(
        repo_root=tmp_path,
        artifact_registry_path=tmp_path / "artifact_index.json",
        cache_dir=tmp_path / "cache",
        source_materializer=materializer,
    )


def test_c06_end_to_end_uses_real_single_source_quality_and_writeback(
    tmp_path: Path,
) -> None:
    materializer = RecordingMaterializer()
    output_dir = tmp_path / "run"

    summary = run_product_contract_experiment(
        case=_case("C06"),
        planner="fixed",
        output_dir=output_dir,
        execution_mode="end_to_end",
        runtime_executor=_executor(tmp_path, materializer),
    )

    assert materializer.calls == ["raw.osm.road"]
    assert summary["execution_mode"] == "end_to_end"
    assert summary["runtime_status"] == "succeeded"
    assert summary["delivered_layers"] == ["road"]

    runtime = json.loads((output_dir / "runtime_execution.json").read_text("utf-8"))
    layer = runtime["layer_results"][0]
    assert [item["source_id"] for item in layer["source_results"]] == [
        "raw.osm.road",
        "raw.reference.road",
    ]
    assert layer["source_results"][1]["status"] == "skipped_known_unusable"
    assert layer["algorithm_result"]["execution_kind"] == "single_source_passthrough"
    assert layer["algorithm_result"]["selected_algorithm_executed"] is False
    assert layer["quality_report"]["accepted"] is True
    assert (
        layer["quality_report"]["policy_id"]
        == "quality.product_contract.single_source.road.v1"
    )
    assert layer["writeback"]["status"] == "registered"

    quality = json.loads((output_dir / "quality_gate_result.json").read_text("utf-8"))
    assert quality["evidence_origin"] == "real_runtime"
    assert quality["layer_results"][0]["passed"] is True

    registry = json.loads((tmp_path / "artifact_index.json").read_text("utf-8"))
    assert {item["artifact_role"] for item in registry["records"]} == {
        "fusion_result",
        "quality_report",
    }


def test_runtime_materialization_failure_is_not_replaced_by_simulated_quality(
    tmp_path: Path,
) -> None:
    materializer = RecordingMaterializer(fail_sources={"raw.osm.road"})
    output_dir = tmp_path / "failed"

    summary = run_product_contract_experiment(
        case=_case("C06"),
        planner="fixed",
        output_dir=output_dir,
        execution_mode="end_to_end",
        runtime_executor=_executor(tmp_path, materializer),
    )

    assert summary["runtime_status"] == "failed"
    assert summary["delivered_layers"] == []
    assert summary["satisfaction_state"] == "not_satisfied"
    quality = json.loads((output_dir / "quality_gate_result.json").read_text("utf-8"))
    assert quality["evidence_origin"] == "real_runtime"
    assert quality["layer_results"][0]["passed"] is False
    assert quality["layer_results"][0]["gates"][0]["gate"] == "runtime_execution"

    gaps = json.loads((output_dir / "gap_declaration.json").read_text("utf-8"))
    assert ("road", "source_unavailable") in {
        (item["layer"], item["gap_type"]) for item in gaps["gaps"]
    }
    assert not (tmp_path / "artifact_index.json").exists()


def test_runtime_materializes_only_planner_selected_sources(tmp_path: Path) -> None:
    case = _case("C06")
    case["input_sources_status"][1]["status"] = "available"
    decision = _fixed_decision(case)
    decision["layer_decisions"][0]["selected_sources"] = ["raw.osm.road"]
    materializer = RecordingMaterializer()

    result = _executor(tmp_path, materializer).execute(
        case=case,
        planning_decision=decision,
        output_dir=tmp_path / "selected-only",
    )

    assert materializer.calls == ["raw.osm.road"]
    assert result["status"] == "succeeded"
    assert result["layer_results"][0]["selected_sources"] == ["raw.osm.road"]


def test_c04_end_to_end_materializes_all_currently_usable_layers(tmp_path: Path) -> None:
    materializer = RecordingMaterializer()
    output_dir = tmp_path / "c04"

    summary = run_product_contract_experiment(
        case=_case("C04"),
        planner="fixed",
        output_dir=output_dir,
        execution_mode="end_to_end",
        runtime_executor=_executor(tmp_path, materializer),
    )

    assert summary["runtime_status"] == "succeeded"
    assert set(summary["delivered_layers"]) == {"building", "road", "water_type_2"}
    assert set(materializer.calls) == {
        "raw.osm.building",
        "raw.osm.road",
        "raw.hydrorivers.water",
    }
    assert "raw.microsoft.road" not in materializer.calls


def test_c02_end_to_end_keeps_water_semantic_source_rejections_explicit(
    tmp_path: Path,
) -> None:
    materializer = RecordingMaterializer()
    output_dir = tmp_path / "c02"

    summary = run_product_contract_experiment(
        case=_case("C02"),
        planner="fixed",
        output_dir=output_dir,
        execution_mode="end_to_end",
        runtime_executor=_executor(tmp_path, materializer),
    )

    assert summary["runtime_status"] == "partial"
    assert set(summary["delivered_layers"]) == {"building", "road"}
    assert summary["satisfaction_state"] == "not_satisfied"
    assert set(materializer.calls) == {"raw.osm.building", "raw.osm.road"}
    runtime = json.loads((output_dir / "runtime_execution.json").read_text("utf-8"))
    by_layer = {item["layer"]: item for item in runtime["layer_results"]}
    assert by_layer["water_type_1"]["status"] == "failed"
    assert by_layer["water_type_2"]["status"] == "failed"
    assert by_layer["water_type_1"]["source_results"][0]["observed_status"] == "source_mismatch"
    assert by_layer["water_type_2"]["source_results"][0]["observed_status"] == "stale"


def test_two_usable_road_sources_invoke_existing_v7_fusion_algorithm(
    tmp_path: Path,
) -> None:
    case = deepcopy(_case("C06"))
    case["input_sources_status"] = [
        {
            "source_id": "raw.osm.road",
            "layer": "road",
            "status": "available",
            "coverage": 0.76,
            "freshness": "moderate",
        },
        {
            "source_id": "raw.microsoft.road",
            "layer": "road",
            "status": "available",
            "coverage": 0.65,
            "freshness": "moderate",
        },
    ]
    materializer = RecordingMaterializer()
    output_dir = tmp_path / "dual-road"

    summary = run_product_contract_experiment(
        case=case,
        planner="fixed",
        output_dir=output_dir,
        execution_mode="end_to_end",
        runtime_executor=_executor(tmp_path, materializer),
    )

    runtime = json.loads((output_dir / "runtime_execution.json").read_text("utf-8"))
    algorithm = runtime["layer_results"][0]["algorithm_result"]
    assert materializer.calls == ["raw.osm.road", "raw.microsoft.road"]
    assert algorithm["execution_kind"] == "domain_fusion"
    assert algorithm["selected_algorithm_executed"] is True
    assert algorithm["resolved_algorithm_id"] == "algo.fusion.road.conflation.v7"
    assert Path(algorithm["output_path"]).exists()
    assert summary["runtime_status"] == "succeeded"


def test_planning_only_and_end_to_end_artifacts_are_explicitly_separate(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "planning"
    summary = run_product_contract_experiment(
        case=_case("C06"),
        planner="fixed",
        output_dir=output_dir,
    )

    assert summary["execution_mode"] == "planning_only"
    assert summary["runtime_status"] is None
    assert not (output_dir / "runtime_execution.json").exists()
    quality = json.loads((output_dir / "quality_gate_result.json").read_text("utf-8"))
    assert quality["evidence_origin"] == "controlled_status_simulation"
    manifest = json.loads((output_dir / "delivery_manifest.json").read_text("utf-8"))
    assert manifest["execution_mode"] == "planning_only"
    assert "runtime_execution.json" not in manifest["machine_outputs"]


def test_invalid_execution_mode_fails_before_planning(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not a valid ExperimentExecutionMode"):
        run_product_contract_experiment(
            case=_case("C06"),
            planner="fixed",
            output_dir=tmp_path,
            execution_mode="mixed",
        )
