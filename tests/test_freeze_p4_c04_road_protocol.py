from pathlib import Path

import pytest

from scripts.freeze_p4_c04_road_protocol import (
    _validate_selected_plan,
    _validate_stage_semantics,
    build_p4_c04_freeze,
    verify_p4_c04_freeze,
    write_p4_c04_freeze,
)


REPO_ROOT = Path(__file__).parents[1]
FORMAL_ROOT = Path(r"D:\code\fusionagent-evidence\p3-planning-formal\2026-08-13-deepseek-v4-flash-formal-r1")
READINESS = Path(r"D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-13-readiness-audit-v2.json")
ASSET_MANIFEST = REPO_ROOT / "docs" / "thesis" / "manifests" / "2026-07-20-c02-c04-c06-real-data.json"
CASE_MANIFEST = REPO_ROOT / "docs" / "current" / "research-case-manifest-v1.json"
PRIOR_FAILURE = Path(
    r"D:\code\fusionagent-evidence\p4-planning-e2e\2026-08-14-c04-road-e2e-r2\experiment_failure.correction.json"
)


@pytest.mark.realdata
def test_real_c04_protocol_freeze_hashes_assets_and_fails_closed_on_tamper(tmp_path: Path) -> None:
    if not FORMAL_ROOT.exists() or not READINESS.exists() or not PRIOR_FAILURE.exists():
        pytest.skip("Formal/readiness evidence is unavailable")
    evidence_root = tmp_path / "future-evidence"
    payload = build_p4_c04_freeze(
        formal_root=FORMAL_ROOT,
        readiness_path=READINESS,
        asset_manifest_path=ASSET_MANIFEST,
        case_manifest_path=CASE_MANIFEST,
        evidence_root=evidence_root,
        prior_failure_path=PRIOR_FAILURE,
        implementation_commit="commit-under-test",
    )
    output = tmp_path / "freeze"
    audit = write_p4_c04_freeze(output, payload)

    assert audit["passed"] is True
    assert payload["protocol"]["protocol_ready"] is True
    assert payload["protocol"]["execution_ready"] is True
    assert payload["protocol"]["execution_blockers"] == []
    assert payload["protocol"]["previous_attempt"]["run_id"] == "3c9624f31826468e8308e5bd82580bc4"
    assert payload["execution_config"]["case_identity"]["run_id"] == "p4-c04-road-caracas-r3"
    assert payload["workflow_plan"]["repair_strategies"]
    assert payload["protocol"]["evaluation_boundary"]["planning_rubric_mismatch_preserved"] is True
    by_id = {item["source_id"]: item for item in payload["asset_inventory"]["sources"]}
    assert by_id["raw.osm.road"]["feature_count"] == 16279
    assert by_id["raw.microsoft.road"]["feature_count"] == 11809

    selected_path = output / "selected_plan.json"
    selected_path.write_text(selected_path.read_text(encoding="utf-8").replace('"degraded"', '"planned"', 1), encoding="utf-8")
    assert verify_p4_c04_freeze(output)["passed"] is False


def test_stage_contract_rejects_microsoft_in_provisional_stage() -> None:
    config = {
        "stages": [
            {
                "stage_id": "osm_provisional",
                "active_source_ids": ["raw.osm.road", "raw.microsoft.road"],
                "delayed_source_ids": ["raw.microsoft.road"],
            },
            {
                "stage_id": "microsoft_arrival",
                "active_source_ids": [
                    "raw.osm.road",
                    "raw.microsoft.road",
                    "aoi.venezuela_capital_district",
                ],
            },
        ],
        "runtime": {"llm_calls": 0, "fallback": "forbidden"},
    }
    with pytest.raises(ValueError, match="must not be active"):
        _validate_stage_semantics(config)
