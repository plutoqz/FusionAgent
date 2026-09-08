from __future__ import annotations

import json
from pathlib import Path

from scripts.audit_development_template_package import audit


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/current/benchmark/v2/development_templates"


def test_development_template_package_is_closed_and_authoring_only():
    report = audit(PACKAGE)
    assert report["status"] == "passed_authoring_spec_only", report["failures"]
    assert report["family_count"] == 15
    assert report["generation_ready"] is False
    assert report["provider_calls"] == report["judge_calls"] == 0
    assert report["instances_generated"] == report["formal_result_roots"] == 0


def test_every_v2_extension_is_task_indexed_and_evidence_family_is_five_product():
    manifest = json.loads((PACKAGE / "authoring_manifest.json").read_text(encoding="utf-8"))
    evidence = json.loads((PACKAGE / "base/TF-EVIDENCE-COMPLETENESS.json").read_text(encoding="utf-8"))
    assert {task["task_kind"] for task in evidence["task_state"]["tasks"]} == {"building", "road", "water_polygon", "waterways", "poi"}
    extension = json.loads((PACKAGE / "extensions/TF-EVIDENCE-COMPLETENESS.json").read_text(encoding="utf-8"))
    tasks = {task["task_id"] for task in evidence["task_state"]["tasks"]}
    assert {item["task_id"] for item in extension["v2_extensions"]["algorithm_grounding"]} == tasks
    assert {item["task_id"] for item in extension["v2_extensions"]["quality_evidence"]} == tasks
    assert {item["task_id"] for item in extension["v2_extensions"]["delivery"]} == tasks
    assert all(item["evidence_type"] in {"source_attempt", "execution_trace", "quality_report", "artifact_lineage", "delivery_manifest"} for item in extension["v2_extensions"]["delivery"][0]["evidence_refs"])
    assert manifest["evidence_boundary"]["authoring_fixture_hashes_are_live_gis_artifacts"] is False


def test_package_contains_no_forbidden_product_domains_or_historical_case_ids():
    for path in (PACKAGE / "base").glob("*.json"):
        document = json.loads(path.read_text(encoding="utf-8"))
        document.get("partition_policy", {}).pop("historical_case_ids_forbidden_in_confirmation", None)
        text = json.dumps(document, ensure_ascii=False).lower()
        assert "insar" not in text
        assert "raster" not in text
        assert not any(f'"{case_id}"' in text for case_id in [f"C{i:02d}" for i in range(1, 7)] + [f"H{i:02d}" for i in range(1, 10)])
