from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_template_semantics_manifest import audit


ROOT = Path(__file__).resolve().parents[1]


def test_candidate_manifest_closes_to_kg_and_covers_full_chain():
    result = audit(
        ROOT / "docs/current/method-selection-template-families-v2-candidate.json",
        ROOT / "kg/ontology/v1.0.0/entities.json",
        ROOT / "kg/ontology/v1.0.0/policies.json",
    )
    assert result["status"] == "passed", result["failures"]
    assert result["products"] == ["building", "poi", "road", "water_polygon", "waterways"]
    assert result["provider_calls"] == result["judge_calls"] == result["instances_generated"] == 0


def test_unknown_manifest_id_is_reported_without_mutating_candidate():
    manifest_path = ROOT / "docs/current/method-selection-template-families-v2-candidate.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["families"][0]["algorithm_ids"].append("algo.unknown.v1")
    temp_manifest = ROOT / "tests/fixtures/benchmark_platform/template_semantics_candidate_unknown.json"
    temp_manifest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        result = audit(temp_manifest, ROOT / "kg/ontology/v1.0.0/entities.json", ROOT / "kg/ontology/v1.0.0/policies.json")
        assert result["status"] == "failed"
        assert any(item["reason"] == "unknown_kg_ids" for item in result["failures"])
    finally:
        temp_manifest.unlink()
