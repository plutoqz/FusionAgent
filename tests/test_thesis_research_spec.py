from pathlib import Path


def test_thesis_spec_contains_rqs_claims_and_non_claims() -> None:
    text = Path(
        "docs/superpowers/specs/2026-05-13-thesis-research-spec.md"
    ).read_text(encoding="utf-8")

    assert "RQ1" in text
    assert "RQ2" in text
    assert "RQ3" in text
    assert "KG-decomposed algorithm primitives" in text
    assert "contract-bounded planning and execution with healing" in text
    assert "auditable evidence contract" in text
    assert "no final-product UI claim" in text
    assert "trajectory-to-road" in text


def test_thesis_claims_ledger_maps_primary_claims_to_live_evidence() -> None:
    text = Path(
        "docs/superpowers/specs/2026-05-13-thesis-claims-ledger.md"
    ).read_text(encoding="utf-8")

    assert "C1" in text
    assert "C2" in text
    assert "C3" in text
    assert "2026-04-21-paper-evidence-freeze.md" in text
    assert "c3_replan_fault_recovery" in text
    assert "c8_no_ui_operator_surface" in text
