from __future__ import annotations

import json
from pathlib import Path

from agent.tooling import build_default_tool_registry


def _capability_matrix() -> dict:
    return json.loads(
        Path("docs/superpowers/specs/2026-05-06-capability-matrix.json").read_text(
            encoding="utf-8"
        )
    )


def test_building_multisource_remains_research_utility_boundary() -> None:
    matrix = _capability_matrix()
    item = {
        capability["capability_id"]: capability
        for capability in matrix["themes"]["building"]
    }["building.multisource_fusion_semantics"]

    assert item["status"] == "optional"
    assert item["claim_state"] == "research_utility"
    assert "runtime_output/fused_buildings.gpkg" in item["evidence_contract"]


def test_building_multisource_height_runtime_is_bounded_supported() -> None:
    matrix = _capability_matrix()
    item = {
        capability["capability_id"]: capability
        for capability in matrix["themes"]["building"]
    }["building.multisource_height_raster_runtime"]

    assert item["status"] == "core"
    assert item["claim_state"] == "bounded_supported"
    assert "source_semantic_contract.json" in item["evidence_contract"]


def test_poi_runtime_claim_remains_bounded_supported() -> None:
    matrix = _capability_matrix()
    item = {
        capability["capability_id"]: capability
        for capability in matrix["themes"]["poi"]
    }["poi.task_driven_auto"]

    assert item["status"] == "core"
    assert item["claim_state"] == "bounded_supported"


def test_trajectory_to_road_tool_is_reserved_only() -> None:
    registry = build_default_tool_registry()
    spec = registry.require("algo.transform.trajectory_to_road_candidate")

    assert spec.error_policy["reserved"] == "true"
    assert spec.handler_name == "_handle_reserved_trajectory_pretransform"
