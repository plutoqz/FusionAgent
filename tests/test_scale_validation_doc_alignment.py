from pathlib import Path


def test_scale_validation_docs_keep_generic_claim_wording() -> None:
    ops = Path("docs/v2-operations.md").read_text(encoding="utf-8")
    inventory = Path(
        "docs/superpowers/specs/2026-05-06-capability-inventory.md"
    ).read_text(encoding="utf-8")
    review = Path(
        "docs/superpowers/specs/2026-05-06-capability-consolidation-review.md"
    ).read_text(encoding="utf-8")
    library = Path("docs/fusioncode-algorithm-library.md").read_text(encoding="utf-8")
    ledger = Path(
        "docs/superpowers/specs/2026-05-14-fusioncode-parity-ledger.md"
    ).read_text(encoding="utf-8")

    assert "Validation-dataset example commands" in ops
    assert "not a country-specific capability boundary" in ops
    assert "inspection_summary.json" in ops
    assert "building.scale_validation_cleanup_rules" in inventory
    assert "building.benin_cleanup_rules" not in inventory
    assert "Capability ids stay generic" in inventory
    assert "inspection_summary.json" in inventory
    assert "checked-in scale-validation dataset wording" in review
    assert "Benin-labeled script names remain dataset examples, not capability names" in review
    assert "Treat those names as validation-dataset entrypoints" in library
    assert "inspection_summary.json" in library
    assert "D5 final wording cleanup: completed" in ledger
