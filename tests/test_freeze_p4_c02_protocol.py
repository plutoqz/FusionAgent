from pathlib import Path

import pytest

from scripts.freeze_p4_c02_protocol import build_p4_c02_freeze, verify_p4_c02_freeze, write_p4_c02_freeze
from scripts.run_p4_c02_e2e import preflight_p4_c02_runner


REPO_ROOT = Path(__file__).parents[1]
FORMAL_ROOT = Path(r"D:\code\fusionagent-evidence\p3-planning-formal\2026-08-13-deepseek-v4-flash-formal-r1")
INVENTORY = Path(r"D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c02-asset-inventory-s2-r3\asset_inventory.json")
S1_AUDIT = Path(r"D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c02-selected-resolved-s1-r2\selected_resolved_audit.json")
CASE_MANIFEST = REPO_ROOT / "docs" / "current" / "research-case-manifest-v1.json"


@pytest.mark.realdata
def test_real_c02_v2_freeze_hashes_runner_and_fails_closed_on_tamper(tmp_path: Path) -> None:
    if not all(path.exists() for path in (FORMAL_ROOT, INVENTORY, S1_AUDIT, CASE_MANIFEST)):
        pytest.skip("Formal C02 evidence is unavailable")
    payload = build_p4_c02_freeze(
        formal_root=FORMAL_ROOT,
        inventory_path=INVENTORY,
        s1_audit_path=S1_AUDIT,
        case_manifest_path=CASE_MANIFEST,
        evidence_root=tmp_path / "future-evidence",
        implementation_commit="commit-under-test",
    )
    output = tmp_path / "freeze"
    audit = write_p4_c02_freeze(output, payload)

    assert audit["passed"] is True
    assert payload["protocol"]["protocol_id"] == "fusionagent.p4.c02-water-road-e2e.v2"
    assert payload["execution_config"]["case_identity"]["run_id"] == "p4-c02-water-road-caracas-r2"
    assert "scripts/run_p4_c02_e2e.py" in payload["protocol"]["implementation_files"]
    assert "schemas/task_kind.py" in payload["protocol"]["implementation_files"]
    assert preflight_p4_c02_runner(output)["passed"] is True

    stage_path = output / "stage_plans.json"
    stage_path.write_text(stage_path.read_text(encoding="utf-8").replace('"step": 1', '"step": 2', 1), encoding="utf-8")
    assert verify_p4_c02_freeze(output)["passed"] is False
