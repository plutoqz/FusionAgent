from __future__ import annotations

import json
import hashlib
from pathlib import Path

from jsonschema import Draft202012Validator
import pytest

from benchmark_platform.template_v2 import V2TemplateValidationError, semantic_failures, validate_v2_extension_document
from scripts.audit_template_authoring_contracts import _schema_probe_failures, _valid_envelope, audit


ROOT = Path(__file__).resolve().parents[1]


def test_v2_candidate_contracts_and_matrix_close_over_approved_semantics():
    result = audit(
        ROOT / "docs/current/method-selection-template-authoring-contracts-v2-candidate.json",
        ROOT / "docs/current/method-selection-template-families-v2-candidate.json",
        ROOT / "schemas/benchmark_template_v2_candidate_extension.schema.json",
        ROOT / "docs/current/benchmark/v2/capability_matrix_candidate.json",
    )
    assert result["status"] == "passed_machine_only", result["failures"]
    assert result["frozen_inputs_valid"] is True
    assert result["schema_probes_passed"] is True
    assert result["development_only"] is True
    assert result["provider_calls"] == result["judge_calls"] == result["instances_generated"] == 0


def test_v2_schema_is_an_extension_envelope_and_does_not_change_v1():
    schema = json.loads((ROOT / "schemas/benchmark_template_v2_candidate_extension.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["status"]["const"] == "v2_candidate"
    assert schema["properties"]["base_template_schema_id"]["const"].endswith("benchmark-template.v1.json")
    assert set(schema["$defs"]) == {"lineageBinding", "aoi", "acquisition", "algorithmGrounding", "qualityEvidence", "delivery"}


def test_platform_v2_validator_combines_schema_and_lineage_semantics():
    schema = json.loads((ROOT / "schemas/benchmark_template_v2_candidate_extension.schema.json").read_text(encoding="utf-8"))
    valid = _valid_envelope("algorithm_grounding")
    assert validate_v2_extension_document(valid, schema).passed is True
    valid["v2_extensions"]["algorithm_grounding"]["required_input_source_ids"].append("raw.gns.poi")
    valid["lineage_binding"]["source_ids"].append("raw.gns.poi")
    with pytest.raises(V2TemplateValidationError, match="missing_input"):
        validate_v2_extension_document(valid, schema)


def test_v2_schema_enforces_aoi_and_manual_preload_cross_field_constraints():
    schema = json.loads((ROOT / "schemas/benchmark_template_v2_candidate_extension.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validate = Draft202012Validator(schema).validate
    validate({
        "base_template_schema_id": "https://fusionagent.local/schemas/benchmark-template.v1.json",
        "base_template_id": "TF-PROBE",
        "base_template_sha256": "sha256:" + "a" * 64,
        "frozen_plan_sha256": "sha256:" + "a" * 64,
        "lineage_binding": {"contract_ids": ["contract.product.poi.v1"], "source_ids": ["raw.gns.poi"], "algorithm_ids": ["algo.fusion.poi.v1"], "artifact_hashes": ["sha256:" + "a" * 64]},
        "status": "v2_candidate",
        "v2_extensions": {"acquisition": [{"attempt_id": "A1", "source_id": "raw.gns.poi", "attempt_status": "succeeded", "materialization_mode": "manual_preload", "remote_success": False, "manual_preload": True, "failure_code": None, "retry_eligible": False, "artifact_hash": "sha256:" + "a" * 64}]},
    })
    invalid = {
        "base_template_schema_id": "https://fusionagent.local/schemas/benchmark-template.v1.json",
        "base_template_id": "TF-PROBE",
        "base_template_sha256": "sha256:" + "a" * 64,
        "frozen_plan_sha256": "sha256:" + "a" * 64,
        "lineage_binding": {"contract_ids": ["contract.product.poi.v1"], "source_ids": ["raw.gns.poi"], "algorithm_ids": ["algo.fusion.poi.v1"], "artifact_hashes": ["sha256:" + "a" * 64]},
        "status": "v2_candidate",
        "v2_extensions": {"acquisition": [{"attempt_id": "A1", "source_id": "raw.gns.poi", "attempt_status": "succeeded", "materialization_mode": "manual_preload", "remote_success": True, "manual_preload": True, "failure_code": None, "retry_eligible": False, "artifact_hash": "sha256:" + "a" * 64}]},
    }
    errors = list(Draft202012Validator(schema).iter_errors(invalid))
    assert errors


def test_v2_schema_forbids_relaxed_hard_quality_checks():
    schema = json.loads((ROOT / "schemas/benchmark_template_v2_candidate_extension.schema.json").read_text(encoding="utf-8"))
    payload = {
        "base_template_schema_id": "https://fusionagent.local/schemas/benchmark-template.v1.json",
        "base_template_id": "TF-PROBE",
        "base_template_sha256": "sha256:" + "a" * 64,
        "frozen_plan_sha256": "sha256:" + "a" * 64,
        "lineage_binding": {"contract_ids": ["contract.product.poi.v1"], "source_ids": ["raw.osm.poi"], "algorithm_ids": ["algo.fusion.poi.v1"], "artifact_hashes": ["sha256:" + "a" * 64]},
        "status": "v2_candidate",
        "v2_extensions": {"quality_evidence": {"source_mode": "single_source", "source_ids": ["raw.osm.poi"], "quality_gate_result": "degraded", "hard_checks": [{"check_id": key, "status": "pass", "relaxed": key == "geometry_type"} for key in ("geometry_type", "invalid_geometry_rate", "source_lineage", "required_fields")], "soft_adaptations": [], "evidence_manifest": "evidence.json", "artifact_lineage": ["artifact:a"]}},
    }
    assert list(Draft202012Validator(schema).iter_errors(payload))


def test_independent_review_counterexamples_are_rejected():
    schema = json.loads((ROOT / "schemas/benchmark_template_v2_candidate_extension.schema.json").read_text(encoding="utf-8"))
    assert _schema_probe_failures(schema) == []


def test_lineage_and_algorithm_subset_are_checked_semantically():
    sha = "sha256:" + "a" * 64
    payload = {
        "lineage_binding": {"source_ids": ["raw.osm.poi"], "algorithm_ids": ["algo.fusion.poi.v1"], "artifact_hashes": [sha]},
        "v2_extensions": {
            "algorithm_grounding": {"selected_algorithm_id": "algo.fusion.poi.v1", "capability_status": "compatible", "required_input_source_ids": ["raw.osm.poi", "raw.gns.poi"], "materialized_input_source_ids": ["raw.osm.poi"], "missing_required_input_source_ids": []}
        },
    }
    failures = semantic_failures(payload)
    assert "algorithm_source_not_in_lineage" in failures
    assert "compatible_algorithm_missing_input" in failures


def test_authoring_audit_rejects_registered_source_with_wrong_product_role(tmp_path):
    semantic_path = ROOT / "docs/current/method-selection-template-families-v2-candidate.json"
    contract_path = ROOT / "docs/current/method-selection-template-authoring-contracts-v2-candidate.json"
    semantics = json.loads(semantic_path.read_text(encoding="utf-8"))
    contracts = json.loads(contract_path.read_text(encoding="utf-8"))
    semantics["families"][0]["source_ids"].append("raw.osm.road")
    contracts["families"][0]["source_ids"].append("raw.osm.road")
    tampered_semantics = tmp_path / "semantics.json"
    tampered_contracts = tmp_path / "contracts.json"
    semantic_bytes = (json.dumps(semantics, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    tampered_semantics.write_bytes(semantic_bytes)
    contracts["source_manifest_sha256"] = "sha256:" + hashlib.sha256(semantic_bytes).hexdigest()
    tampered_contracts.write_text(json.dumps(contracts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = audit(tampered_contracts, tampered_semantics, ROOT / "schemas/benchmark_template_v2_candidate_extension.schema.json", ROOT / "docs/current/benchmark/v2/capability_matrix_candidate.json", repo_root=ROOT)
    assert result["status"] == "failed"
    assert any(item["reason"] == "invalid_source_role" for item in result["failures"])


def test_authoring_audit_rejects_registered_conditional_raster_source(tmp_path):
    semantic_path = ROOT / "docs/current/method-selection-template-families-v2-candidate.json"
    contract_path = ROOT / "docs/current/method-selection-template-authoring-contracts-v2-candidate.json"
    semantics = json.loads(semantic_path.read_text(encoding="utf-8"))
    contracts = json.loads(contract_path.read_text(encoding="utf-8"))
    source_id = "raw.google.building_height.raster"
    semantics["families"][0]["source_ids"].append(source_id)
    contracts["families"][0]["source_ids"].append(source_id)
    tampered_semantics = tmp_path / "semantics-raster.json"
    tampered_contracts = tmp_path / "contracts-raster.json"
    semantic_bytes = (json.dumps(semantics, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    tampered_semantics.write_bytes(semantic_bytes)
    contracts["source_manifest_sha256"] = "sha256:" + hashlib.sha256(semantic_bytes).hexdigest()
    tampered_contracts.write_text(json.dumps(contracts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = audit(tampered_contracts, tampered_semantics, ROOT / "schemas/benchmark_template_v2_candidate_extension.schema.json", ROOT / "docs/current/benchmark/v2/capability_matrix_candidate.json", repo_root=ROOT)
    assert result["status"] == "failed"
    assert {item["reason"] for item in result["failures"]} & {"forbidden_domain", "invalid_source_role"}
