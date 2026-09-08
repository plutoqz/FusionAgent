from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark_platform.oracle import OracleError, solve_template_oracle


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/benchmark_platform/template_contract_valid.json"


def template() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_fixture_oracle_is_solvable_and_proof_is_deterministic():
    first = solve_template_oracle(template())
    second = solve_template_oracle(template())
    assert first == second
    assert first.solver_id == "finite-state-task-contract.v1"
    assert first.proof_hash.startswith("sha256:")
    assert first.task_plans[0].valid_combinations[0]["delivery_state"] == "planned"


def test_missing_task_constraint_fails_closed():
    value = template()
    value["oracle"]["task_constraints"] = []
    with pytest.raises(OracleError, match="no constraint"):
        solve_template_oracle(value)


def test_forbidden_source_and_invalid_delivery_are_rejected():
    value = template()
    value["oracle"]["task_constraints"][0]["forbidden_source_ids"] = ["source.hidden"]
    value["oracle"]["task_constraints"][0]["allowed_delivery_states"] = ["final"]
    with pytest.raises(OracleError, match="outside oracle"):
        solve_template_oracle(value)
