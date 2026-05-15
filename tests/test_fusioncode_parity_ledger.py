from pathlib import Path


def test_fusioncode_parity_ledger_tracks_required_families_and_claims() -> None:
    text = Path(
        "docs/superpowers/specs/2026-05-14-fusioncode-parity-ledger.md"
    ).read_text(encoding="utf-8")

    assert "building decomposed multi-source workflow" in text
    assert "building raster presence / height primitives" in text
    assert "road segment topology fusion" in text
    assert "water line fusion" in text
    assert "water polygon fusion" in text
    assert "poi geohash neighbor fusion" in text
    assert "`research_utility`" in text
    assert "`runtime_supported`" in text
    assert "`bounded_supported`" in text
    assert "smoke-road-gilgit-city-fusioncode-inspection-8012.json" in text
    assert "smoke-water-nairobi-fusioncode-inspection-8012.json" in text
    assert "smoke-poi-nairobi-fusioncode-inspection-8012.json" in text
    assert "D4 smoke / inspection evidence: completed" in text
