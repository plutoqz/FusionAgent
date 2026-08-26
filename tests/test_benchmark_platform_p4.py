from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from benchmark_platform.canonical import canonical_sha256
from benchmark_platform.generator import GeneratedMember, GeneratedUnit
from benchmark_platform.relations import RelationValidationError, validate_relations
from benchmark_platform.views import ViewProjectionError, project_views


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/benchmark_platform/template_contract_valid.json"


def base_template() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def member(index: int, payload: dict) -> GeneratedMember:
    return GeneratedMember(member_index=index, member_payload=payload, member_sha256=canonical_sha256(payload))


def unit(unit_type: str, payloads: list[dict]) -> GeneratedUnit:
    members = tuple(member(index, payload) for index, payload in enumerate(payloads))
    return GeneratedUnit(
        instance_id="BDV1-DEV-BC-CAUSAL-01-000",
        template_family_id="TF-CONTRACT-FIXTURE",
        capability_cell_id="BC-CAUSAL-01",
        partition="development",
        unit_index=0,
        unit_type=unit_type,
        seed=1,
        template_sha256="sha256:" + "1" * 64,
        members=members,
        instance_sha256="sha256:" + "2" * 64,
    )


def configure(template: dict, unit_type: str, assertion: dict, minimum: int) -> dict:
    template["experiment_unit"] = {"unit_type": unit_type, "relation_id": "REL-P4-FIXTURE", "minimum_members": minimum, "relation_assertions": [assertion]}
    template["oracle"]["relation_assertion_ids"] = [assertion["assertion_id"]]
    return template


ALLOWED_FAILURES = {
    "planning.structure_invalid",
    "planning.causal_response",
    "planning.wording_instability",
    "projection.cross_task_source_pollution",
    "planning.invalid_delivery_transition",
}


def test_single_evidence_presence() -> None:
    template = configure(base_template(), "single", {"assertion_id": "A1", "kind": "evidence_presence", "left_path": "$.task_state", "operator": "present"}, 1)
    report = validate_relations(unit("single", [copy.deepcopy(template)]), template, "planning.structure_invalid", ALLOWED_FAILURES)
    assert report.passed is True


def test_counterfactual_pair_has_one_causal_change() -> None:
    template = configure(base_template(), "counterfactual_pair", {"assertion_id": "A1", "kind": "causal_change", "left_path": "$.task_state.tasks[0].task_kind", "operator": "not_equals"}, 2)
    template["variables"]["causal_variables"] = [{"variable_id": "VAR-KIND", "json_path": "$.task_state.tasks[0].task_kind", "value_type": "string", "allowed_values": ["road", "building"], "mutation_role": "causal"}]
    template["variables"]["invariants"] = [{"variable_id": "VAR-REGIME", "json_path": "$.task_state.resource_regime", "value_type": "string", "allowed_values": ["offline", "changed"], "mutation_role": "invariant"}]
    first, second = copy.deepcopy(template), copy.deepcopy(template)
    second["task_state"]["tasks"][0]["task_kind"] = "building"
    assert validate_relations(unit("counterfactual_pair", [first, second]), template, "planning.causal_response", ALLOWED_FAILURES).passed is True
    second["task_state"]["resource_regime"] = "changed"
    failed = validate_relations(unit("counterfactual_pair", [first, second]), template, "planning.causal_response", ALLOWED_FAILURES)
    assert failed.passed is False
    assert failed.primary_failure_class == "planning.causal_response"


def test_invariant_set_allows_only_nuisance_change() -> None:
    template = configure(base_template(), "invariant_set", {"assertion_id": "A1", "kind": "semantic_equivalence", "left_path": "$.task_state.resource_regime", "operator": "equals"}, 2)
    template["variables"]["nuisance_variables"] = [{"variable_id": "VAR-DISASTER", "json_path": "$.task_state.disaster_type", "value_type": "string", "allowed_values": ["a", "b"], "mutation_role": "nuisance"}]
    first, second = copy.deepcopy(template), copy.deepcopy(template)
    second["task_state"]["disaster_type"] = "b"
    assert validate_relations(unit("invariant_set", [first, second]), template, "planning.wording_instability", ALLOWED_FAILURES).passed is True
    second["task_state"]["resource_regime"] = "online"
    assert validate_relations(unit("invariant_set", [first, second]), template, "planning.wording_instability", ALLOWED_FAILURES).passed is False


def test_composition_family_detects_cross_task_pollution() -> None:
    template = configure(base_template(), "composition_family", {"assertion_id": "A1", "kind": "task_local_composition", "left_path": "$.task_state.tasks", "operator": "present"}, 2)
    second_task = copy.deepcopy(template["task_state"]["tasks"][0]); second_task["task_id"] = "TASK-BUILDING-02"; second_task["task_kind"] = "building"
    template["task_state"]["tasks"].append(second_task)
    first, second = copy.deepcopy(template), copy.deepcopy(template)
    second["task_state"]["tasks"][0]["task_kind"] = "poi"
    assert validate_relations(unit("composition_family", [first, second]), template, "projection.cross_task_source_pollution", ALLOWED_FAILURES).passed is True
    second["task_state"]["tasks"][1]["task_kind"] = "poi"
    assert validate_relations(unit("composition_family", [first, second]), template, "projection.cross_task_source_pollution", ALLOWED_FAILURES).passed is False


def test_temporal_trace_validates_transition_and_step_order() -> None:
    template = configure(base_template(), "temporal_trace", {"assertion_id": "A1", "kind": "temporal_transition", "left_path": "$.task_state.tasks[0].delivery_history[0].state", "operator": "transitions_to", "expected_value": "final"}, 2)
    first, second = copy.deepcopy(template), copy.deepcopy(template)
    first["task_state"]["tasks"][0]["delivery_history"] = [{"step": 1, "state": "planned", "evidence_ref": "E1"}]
    second["task_state"]["tasks"][0]["delivery_history"] = [{"step": 1, "state": "final", "evidence_ref": "E2"}]
    assert validate_relations(unit("temporal_trace", [first, second]), template, "planning.invalid_delivery_transition", ALLOWED_FAILURES).passed is True
    second["task_state"]["tasks"][0]["delivery_history"].append({"step": 1, "state": "superseded", "evidence_ref": "E3"})
    assert validate_relations(unit("temporal_trace", [first, second]), template, "planning.invalid_delivery_transition", ALLOWED_FAILURES).passed is False


def test_views_use_allowlists_and_keep_oracle_out_of_planner() -> None:
    template = base_template()
    projected = project_views(template, template["views"])
    assert projected.planner.payload == {"task_state": template["task_state"]}
    assert projected.evaluator.payload == {"oracle": template["oracle"]}
    assert "oracle" not in projected.planner.payload
    assert projected.leakage_audit.passed is True


def test_planner_forbidden_path_overlap_fails_closed() -> None:
    template = base_template()
    contract = copy.deepcopy(template["views"])
    contract["planner_visible_paths"].append("$.oracle")
    with pytest.raises(ViewProjectionError) as error:
        project_views(template, contract)
    assert error.value.failures[0].details["code"] == "forbidden_path_visible"


def test_unknown_failure_class_fails_closed() -> None:
    template = configure(base_template(), "single", {"assertion_id": "A1", "kind": "evidence_presence", "left_path": "$.task_state", "operator": "present"}, 1)
    with pytest.raises(RelationValidationError) as error:
        validate_relations(unit("single", [copy.deepcopy(template)]), template, "unknown.failure", ALLOWED_FAILURES)
    assert error.value.failures[0].details["code"] == "unknown_failure_class"


def test_recursive_identity_leak_fails_closed() -> None:
    template = base_template()
    template["task_state"]["global_observations"]["run_id"] = "hidden-run"
    with pytest.raises(ViewProjectionError) as error:
        project_views(template, template["views"])
    assert error.value.failures[0].details["code"] == "gold_value_leak"


def test_evaluator_only_subtree_leak_fails_closed() -> None:
    template = base_template()
    template["task_state"]["global_observations"]["leaked_gold"] = copy.deepcopy(template["oracle"])
    with pytest.raises(ViewProjectionError) as error:
        project_views(template, template["views"])
    assert error.value.failures[0].details["code"] == "gold_value_leak"
