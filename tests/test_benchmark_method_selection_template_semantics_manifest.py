from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs/current/method-selection-template-families-v2-candidate.json"


def test_semantics_manifest_has_fifteen_bounded_families_and_four_l4_candidates():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    families = payload["families"]
    assert len(families) == 15
    assert payload["approved_family_ids"] == [item["family_id"] for item in families]
    assert len({item["family_id"] for item in families}) == 15
    assert sum(item["complexity"] == "L4" for item in families) == 4
    assert "insar" in payload["forbidden_domains"]
    assert all("raster" not in json.dumps(item, ensure_ascii=False).lower() for item in families)
    assert payload["decisions"]["manual_preload"].startswith("allowed")
    assert payload["decisions"]["single_source"].startswith("soft_degradation")
    assert set(payload["historical_exclusions"]) == {f"C{i:02d}" for i in range(1, 7)} | {f"H{i:02d}" for i in range(1, 10)}


def test_aoi_and_acquisition_are_explicit_v2_candidates():
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_id = {item["family_id"]: item for item in payload["families"]}
    assert by_id["TF-AOI-RESOLUTION-BOUNDARY"]["status"] == "v2_candidate"
    assert by_id["TF-VECTOR-ACQUISITION-FAILURE"]["status"] == "v2_candidate"
    assert by_id["TF-EVIDENCE-COMPLETENESS"]["status"] == "v2_candidate"
    assert by_id["TF-DELIVERY-STATE-TRACE"]["status"] == "v2_candidate"
