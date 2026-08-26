from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from benchmark_platform.design_loader import load_frozen_design_bundle
from benchmark_platform.generator import (
    GenerationRequest,
    GeneratorError,
    generate_development,
)


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs/current/benchmark/v1"
FIXTURE = ROOT / "tests/fixtures/benchmark_platform/template_contract_valid.json"


def template_for_generation() -> dict:
    template = json.loads(FIXTURE.read_text(encoding="utf-8"))
    template["template_family_id"] = "TF-CONTRACT-REQUIREDNESS"
    template["capability_cell_ids"] = ["BC-CAUSAL-01"]
    template["crosswalk"]["references"][0]["reference_id"] = "contract.road.fused.v1"
    template["task_state"]["tasks"][0]["contract_ids"] = ["contract.road.fused.v1"]
    template["generation"]["seed_namespace"] = "fusionagent-benchmark-v1-development"
    template["generation"]["instance_id_pattern"] = "^BDV1-DEV-BC-[A-Z0-9-]+-[0-9]{3}$"
    return template


def request(**overrides) -> GenerationRequest:
    values = {
        "partition": "development",
        "capability_cell_id": "BC-CAUSAL-01",
        "unit_index": 0,
        "seed_namespace": "fusionagent-benchmark-v1-development",
        "master_seed": 2026081901,
    }
    values.update(overrides)
    return GenerationRequest(**values)


def test_development_generation_is_deterministic_and_in_memory() -> None:
    bundle = load_frozen_design_bundle(str(DESIGN), repo_root=str(ROOT))
    template = template_for_generation()
    first = generate_development(bundle, template, request())
    second = generate_development(bundle, copy.deepcopy(template), request())
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    unit = first.units[0]
    assert unit.instance_id == "BDV1-DEV-BC-CAUSAL-01-000"
    assert unit.partition == "development"
    assert len(unit.members) == 1
    assert first.attempts[0].status == "valid"
    assert not Path(r"D:\code\fusionagent-evidence\benchmark-platform\development-v1").exists()


@pytest.mark.parametrize(
    "overrides,code",
    [
        ({"partition": "independent_confirmation"}, "non_development_partition"),
        ({"seed_namespace": "wrong"}, "seed_mismatch"),
        ({"master_seed": 99}, "seed_mismatch"),
        ({"max_attempts": 4}, "attempt_limit"),
        ({"capability_cell_id": "BC-UNKNOWN-01"}, "unknown_cell"),
    ],
)
def test_generation_fail_closed(overrides, code: str) -> None:
    bundle = load_frozen_design_bundle(str(DESIGN), repo_root=str(ROOT))
    with pytest.raises(GeneratorError) as error:
        generate_development(bundle, template_for_generation(), request(**overrides))
    assert error.value.failures[0].details["code"] == code


def test_invalid_template_is_rejected_before_member_creation() -> None:
    bundle = load_frozen_design_bundle(str(DESIGN), repo_root=str(ROOT))
    template = template_for_generation()
    template["capability_cell_ids"] = ["BC-CAUSAL-02"]
    with pytest.raises(GeneratorError) as error:
        generate_development(bundle, template, request())
    assert error.value.failures[0].details["code"] == "invalid_member"
