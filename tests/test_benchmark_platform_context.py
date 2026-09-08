from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark_platform.context import CanonicalContextError, build_canonical_context
from benchmark_platform.crosswalk import CrosswalkError
from benchmark_platform.design_loader import load_frozen_design_bundle


ROOT = Path(__file__).resolve().parents[1]


def _bundle():
    return load_frozen_design_bundle(str(ROOT / "docs/current/benchmark/v1"), repo_root=str(ROOT))


def _template():
    template = json.loads((ROOT / "tests/fixtures/benchmark_platform/template_contract_valid.json").read_text(encoding="utf-8"))
    task = template["task_state"]["tasks"][0]
    task["contract_ids"] = ["contract.product.road.v1"]
    template["crosswalk"]["references"] = [
        {"reference_id": "contract.product.road.v1", "reference_type": "contract", "used_by_task_ids": [task["task_id"]]},
        {"reference_id": "scenario.default.task", "reference_type": "scenario", "used_by_task_ids": [task["task_id"]]},
    ]
    return template


def test_context_is_deterministic_and_hashes_observation():
    bundle = _bundle()
    template = _template()
    first = build_canonical_context(bundle, template, {"weather": "clear"}, scenario_id="scenario.default.task")
    second = build_canonical_context(bundle, template, {"weather": "clear"}, scenario_id="scenario.default.task")
    assert first == second
    assert first.observation_hash.startswith("sha256:")
    assert first.semantic_hash.startswith("sha256:")
    assert first.contract_ids == ("contract.product.road.v1",)


def test_context_rejects_missing_explicit_scenario():
    template = _template()
    with pytest.raises(CanonicalContextError, match="scenario_id must be explicit"):
        build_canonical_context(_bundle(), template, {})


def test_context_rejects_unknown_crosswalk_reference():
    template = _template()
    template["crosswalk"]["references"][0]["reference_id"] = "contract.unknown"
    with pytest.raises(CrosswalkError, match="unknown crosswalk ID"):
        build_canonical_context(_bundle(), template, {}, scenario_id="scenario.default.task")
