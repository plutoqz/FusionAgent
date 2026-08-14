from pathlib import Path

import pytest

from scripts.run_p4_c06_failure_screening import (
    _classify_screening_outcome,
    build_screening_freeze,
    preflight_screening,
    verify_screening_freeze,
    write_screening_freeze,
)


REPO_ROOT = Path(__file__).parents[1]
C04_FREEZE = (
    REPO_ROOT
    / "docs/current/evidence/p4-planning-e2e/2026-08-14-c04-road-protocol-freeze-v5"
)


@pytest.mark.realdata
def test_real_c06_screening_freeze_is_single_candidate_and_tamper_evident(tmp_path: Path) -> None:
    payload = build_screening_freeze(
        c04_freeze_root=C04_FREEZE,
        evidence_root=tmp_path / "future-screening",
        implementation_commit="commit-under-test",
    )
    root = tmp_path / "freeze"
    result = write_screening_freeze(root, payload)

    assert result["freeze_audit"]["passed"] is True
    assert result["preflight"]["passed"] is True
    assert payload["candidate_set"]["candidate_count"] == 1
    assert preflight_screening(root)["passed"] is True

    config_path = root / "execution_config.json"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace('"automatic_retries": 0', '"automatic_retries": 1'),
        encoding="utf-8",
    )
    assert verify_screening_freeze(root)["passed"] is False


@pytest.mark.parametrize(
    ("semantic_valid", "accepted", "adapted", "quality_hash", "expected"),
    [
        (True, False, False, "hash", "quality_gate_rejected_fusion_output"),
        (True, True, True, "hash", "no_quality_failure_observed"),
        (False, None, None, None, "ineligible_non_quality_failure"),
        (True, None, None, None, "ineligible_non_quality_failure"),
    ],
)
def test_screening_outcome_taxonomy(
    semantic_valid: bool,
    accepted: bool | None,
    adapted: bool | None,
    quality_hash: str | None,
    expected: str,
) -> None:
    record = {
        "source_semantic_contract": {"valid": semantic_valid},
        "quality_evaluation": {
            "accepted": accepted,
            "adapted_quality_passed": adapted,
            "report_sha256": quality_hash,
        },
    }

    assert _classify_screening_outcome(record) == expected
