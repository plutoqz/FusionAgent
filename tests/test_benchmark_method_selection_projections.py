from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from benchmark_platform.context import build_canonical_context
from benchmark_platform.design_loader import load_frozen_design_bundle
from benchmark_platform.projections import ProjectionError, project_condition


ROOT = Path(__file__).resolve().parents[1]


def _bundle():
    return load_frozen_design_bundle(str(ROOT / "docs/current/benchmark/v1"), repo_root=str(ROOT))


def _context():
    template = json.loads((ROOT / "tests/fixtures/benchmark_platform/template_contract_valid.json").read_text(encoding="utf-8"))
    task = template["task_state"]["tasks"][0]
    task["contract_ids"] = ["contract.product.road.v1"]
    template["crosswalk"]["references"] = [
        {"reference_id": "contract.product.road.v1", "reference_type": "contract", "used_by_task_ids": [task["task_id"]]},
        {"reference_id": "scenario.default.task", "reference_type": "scenario", "used_by_task_ids": [task["task_id"]]},
        {"reference_id": "catalog.earthquake.road", "reference_type": "source", "used_by_task_ids": [task["task_id"]]},
        {"reference_id": "algo.detect.spatial_conflicts.v1", "reference_type": "algorithm", "used_by_task_ids": [task["task_id"]]},
        {"reference_id": "quality.default.road.v1", "reference_type": "quality_policy", "used_by_task_ids": [task["task_id"]]},
    ]
    return build_canonical_context(_bundle(), template, {"network_state": "offline"}, scenario_id="scenario.default.task")


def _project(condition: str):
    return project_condition(
        condition,
        _context(),
        request={"product": "road"},
        output_schema={"type": "object"},
        workflow_interface={"workflow_id": "workflow.fixture"},
        rules={"rule_set_id": "rules.general.v1"},
        bundle=_bundle(),
    )


def test_all_six_conditions_have_exact_registered_fields_and_stable_hashes():
    conditions = (
        "fixed_workflow", "rules_only", "kg_only", "llm_only", "llm_capability_kg", "llm_full_contract_kg"
    )
    for condition in conditions:
        first = _project(condition)
        second = _project(condition)
        assert tuple(first.payload) == first.spec.visible_fields
        assert first.spec.projection_hash == second.spec.projection_hash
        assert first.trace.leakage_hits == ()


def test_three_llm_conditions_share_common_input_contract():
    projections = {condition: _project(condition) for condition in ("llm_only", "llm_capability_kg", "llm_full_contract_kg")}
    assert len({json.dumps(item.payload["request"], sort_keys=True) for item in projections.values()}) == 1
    assert len({json.dumps(item.payload["output_schema"], sort_keys=True) for item in projections.values()}) == 1
    assert "full_contract_projection" not in projections["llm_capability_kg"].payload
    assert "capability_projection" not in projections["llm_full_contract_kg"].payload
    capability = projections["llm_capability_kg"].payload["capability_projection"]
    assert capability["sources"][0]["source_id"] == "catalog.earthquake.road"
    assert capability["algorithms"][0]["algo_id"] == "algo.detect.spatial_conflicts.v1"
    full = projections["llm_full_contract_kg"].payload["full_contract_projection"]
    assert full["contracts"][0]["contract_id"] == "contract.product.road.v1"
    assert full["quality_policies"][0]["policy_id"] == "quality.default.road.v1"


def test_rules_only_does_not_require_kg_bundle():
    projection = project_condition(
        "rules_only", _context(), request={"product": "road"}, rules={"rule_set_id": "rules.general.v1"}
    )
    assert projection.trace.kg_release_id is None
    assert "kg_query_result" not in projection.payload


def test_kg_condition_requires_bundle_and_forbidden_fields_fail_recursively():
    with pytest.raises(ProjectionError, match="requires the frozen KG bundle"):
        project_condition("kg_only", _context(), request={"product": "road"})
    with pytest.raises(ProjectionError, match="forbidden fields"):
        project_condition(
            "llm_only",
            _context(),
            request={"nested": {"oracle": {"answer": "hidden"}}},
            output_schema={"type": "object"},
        )


def test_kg_copy_change_changes_only_knowledge_projection_hash():
    context = _context()
    bundle = _bundle()
    changed_entities = deepcopy(bundle.kg_entities)
    source = next(item for item in changed_entities["data_sources"] if item["source_id"] == "catalog.earthquake.road")
    source["description"] = "tampered test copy"
    changed_bundle = bundle.model_copy(update={"kg_entities": changed_entities})
    original = project_condition(
        "llm_capability_kg", context, request={"product": "road"}, output_schema={"type": "object"}, bundle=bundle
    )
    changed = project_condition(
        "llm_capability_kg", context, request={"product": "road"}, output_schema={"type": "object"}, bundle=changed_bundle
    )
    assert original.spec.projection_hash != changed.spec.projection_hash
    llm_original = project_condition("llm_only", context, request={"product": "road"}, output_schema={"type": "object"})
    llm_changed = project_condition("llm_only", context, request={"product": "road"}, output_schema={"type": "object"})
    assert llm_original.spec.projection_hash == llm_changed.spec.projection_hash
