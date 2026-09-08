from __future__ import annotations

import json
from pathlib import Path

from benchmark_platform.context import build_canonical_context
from benchmark_platform.design_loader import load_frozen_design_bundle
from benchmark_platform.preflight import run_development_preflight


ROOT = Path(__file__).resolve().parents[1]


def _inputs():
    bundle = load_frozen_design_bundle(str(ROOT / "docs/current/benchmark/v1"), repo_root=str(ROOT))
    template = json.loads((ROOT / "tests/fixtures/benchmark_platform/template_contract_valid.json").read_text(encoding="utf-8"))
    template["template_family_id"] = "TF-PREFLIGHT-CONTRACT"
    template["capability_cell_ids"] = ["BC-CAUSAL-01"]
    task = template["task_state"]["tasks"][0]
    task["contract_ids"] = ["contract.product.road.v1"]
    template["crosswalk"]["references"] = [
        {"reference_id": "contract.product.road.v1", "reference_type": "contract", "used_by_task_ids": [task["task_id"]]},
        {"reference_id": "scenario.default.task", "reference_type": "scenario", "used_by_task_ids": [task["task_id"]]},
    ]
    context = build_canonical_context(bundle, template, {"network_state": "offline"}, scenario_id="scenario.default.task")
    return bundle, template, context


def test_development_preflight_closes_generation_oracle_views_and_blind_packet():
    bundle, template, context = _inputs()
    result = run_development_preflight(
        bundle,
        template,
        context,
        capability_cell_id="BC-CAUSAL-01",
        request_payload={"product": "road"},
        output_schema={"type": "object"},
        rules={"rule_set_id": "rules.general.v1"},
        workflow_interface={"workflow_id": "workflow.fixture"},
    )
    assert result.relation.passed is True
    assert len(result.projections) == len(result.blind_review_items) == 6
    assert all("oracle" not in item.view_payload and "gold" not in item.view_payload for item in result.blind_review_items)
    assert all("condition_id" not in item.view_payload for item in result.blind_review_items)
    assert result.generation.attempts[0].status == "valid"
