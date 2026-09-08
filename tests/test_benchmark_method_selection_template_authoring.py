from __future__ import annotations

import json
from pathlib import Path

from benchmark_platform.design_loader import load_frozen_design_bundle
from benchmark_platform.template_authoring import TemplateFamilyContract, audit_template_family


ROOT = Path(__file__).resolve().parents[1]


def test_template_authoring_contract_closes_schema_crosswalk_oracle_and_exclusions():
    bundle = load_frozen_design_bundle(str(ROOT / "docs/current/benchmark/v1"), repo_root=str(ROOT))
    template = json.loads((ROOT / "tests/fixtures/benchmark_platform/template_contract_valid.json").read_text(encoding="utf-8"))
    template["template_family_id"] = "TF-AUTHORING-CONTRACT"
    task = template["task_state"]["tasks"][0]
    task["contract_ids"] = ["contract.product.road.v1"]
    template["crosswalk"]["references"] = [
        {"reference_id": "contract.product.road.v1", "reference_type": "contract", "used_by_task_ids": [task["task_id"]]},
        {"reference_id": "scenario.default.task", "reference_type": "scenario", "used_by_task_ids": [task["task_id"]]},
    ]
    contract = TemplateFamilyContract(template_family_id="TF-AUTHORING-CONTRACT", product_type="road", complexity_level="L0", coverage_tags=("contract", "veto"), causal_variable_ids=(), invariant_variable_ids=("VAR-TASK-KIND",), nuisance_variable_ids=(), historical_exclusion_checked=True)
    audit = audit_template_family(bundle, template, contract)
    assert audit.passed is True
    assert audit.historical_ids_found == ()
