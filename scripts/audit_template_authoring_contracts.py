from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark_platform.design_loader import load_frozen_design_bundle
from benchmark_platform.template_v2 import semantic_failures


ALLOWED_PRODUCTS = {"building", "road", "water_polygon", "waterways", "poi"}
REQUIRED_TAGS = {"building", "road", "water_polygon", "waterways", "poi", "gap", "veto", "delivery", "recovery"}
EXPECTED_CHAIN = {
    "TF-CONTRACT-REQUIREDNESS": ["planning"], "TF-WORDING-PARAPHRASE": ["planning"],
    "TF-INPUT-ORDER": ["projection", "planning"], "TF-IRRELEVANT-NOISE": ["planning"],
    "TF-CROSS-TASK-PRECEDENCE": ["planning"], "TF-KG-CROSSWALK-MISSING": ["planning"],
    "TF-PLAN-STRUCTURE-INVALID": ["planning"], "TF-VALIDATOR-VETO": ["planning"],
    "TF-ALGORITHM-CAPABILITY-GROUNDING": ["planning", "algorithm"], "TF-SOURCE-AVAILABILITY": ["planning"],
    "TF-AOI-RESOLUTION-BOUNDARY": ["region", "planning"], "TF-VECTOR-ACQUISITION-FAILURE": ["planning", "acquisition", "delivery"],
    "TF-QUALITY-GATE-EVIDENCE": ["acquisition", "algorithm", "quality", "delivery", "evidence"],
    "TF-EVIDENCE-COMPLETENESS": ["planning", "region", "acquisition", "algorithm", "execution", "quality", "delivery", "evidence"],
    "TF-DELIVERY-STATE-TRACE": ["planning", "quality", "delivery", "evidence"],
}
EXPECTED_EXTENSIONS = {
    "TF-ALGORITHM-CAPABILITY-GROUNDING": ["algorithm_grounding"], "TF-AOI-RESOLUTION-BOUNDARY": ["aoi"],
    "TF-VECTOR-ACQUISITION-FAILURE": ["acquisition", "delivery"],
    "TF-QUALITY-GATE-EVIDENCE": ["acquisition", "algorithm_grounding", "quality_evidence", "delivery"],
    "TF-EVIDENCE-COMPLETENESS": ["aoi", "acquisition", "algorithm_grounding", "quality_evidence", "delivery"],
    "TF-DELIVERY-STATE-TRACE": ["quality_evidence", "delivery"],
}
FULL_CHAIN = {"planning", "region", "acquisition", "algorithm", "execution", "quality", "delivery", "evidence"}
FIVE_PRODUCT_REQUIRED_SOURCES = {"raw.osm.building", "raw.microsoft.building", "raw.osm.road", "raw.microsoft.road", "raw.osm.water", "raw.hydrolakes.water", "raw.osm.waterways", "raw.hydrorivers.water", "raw.osm.poi", "raw.gns.poi", "raw.google.poi"}


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _items(value: Any):
    return (item for item in value if isinstance(item, dict)) if isinstance(value, list) else ()


def _policy_ids(policies: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    for value in policies.values():
        if isinstance(value, dict) and isinstance(value.get("policy_id"), str): found.add(value["policy_id"])
        for item in _items(value):
            if isinstance(item.get("policy_id"), str): found.add(item["policy_id"])
    return found


def _algorithm_products(item: dict[str, Any]) -> set[str]:
    task, output = str(item.get("task_type", "")), str(item.get("output_type", ""))
    if task == "building_fusion" or "building.bundle" in output: return {"building"}
    if task == "road_fusion" or "road.bundle" in output: return {"road"}
    if task == "poi_fusion" or "poi.bundle" in output: return {"poi"}
    if "waterways" in output: return {"waterways"}
    if task == "water_fusion": return {"water_polygon"}
    return set()


def _valid_envelope(extension: str) -> dict[str, Any]:
    sha = "sha256:" + "a" * 64
    values = {
        "aoi": {"aoi_candidate_set": ["AOI-1"], "resolution_status": "resolved", "ambiguity_class": "none", "resolved_geometry_hash": sha, "boundary_provenance": "kg:aoi", "cross_aoi_isolation": True},
        "acquisition": [{"attempt_id": "ATTEMPT-1", "source_id": "raw.osm.poi", "attempt_status": "succeeded", "materialization_mode": "local_bundle", "remote_success": False, "manual_preload": False, "failure_code": None, "retry_eligible": False, "artifact_hash": sha}],
        "algorithm_grounding": {"task_id": "TASK-POI", "selected_algorithm_id": "algo.fusion.poi.v1", "capability_status": "compatible", "required_input_source_ids": ["raw.osm.poi"], "materialized_input_source_ids": ["raw.osm.poi"], "missing_required_input_source_ids": []},
        "quality_evidence": {"source_mode": "single_source", "source_ids": ["raw.osm.poi"], "quality_gate_result": "provisional", "hard_checks": [{"check_id": key, "status": "pass", "relaxed": False} for key in ("geometry_type", "invalid_geometry_rate", "source_lineage", "required_fields")], "soft_adaptations": [{"policy_id": "quality.external_degradation.v1", "check_id": "source_contribution_balance", "applied": True}], "evidence_manifest": "evidence.json", "artifact_lineage": ["artifact:poi"]},
        "delivery": {"from_state": "planned", "to_state": "provisional", "transition_reason": "bounded evidence", "evidence_refs": [{"evidence_type": "quality_report", "ref": "quality.json"}], "terminal": True},
    }
    return {"base_template_schema_id": "https://fusionagent.local/schemas/benchmark-template.v1.json", "base_template_id": "TF-PROBE", "base_template_sha256": sha, "frozen_plan_sha256": sha, "lineage_binding": {"contract_ids": ["contract.product.poi.v1"], "source_ids": ["raw.osm.poi"], "algorithm_ids": ["algo.fusion.poi.v1"], "artifact_hashes": [sha]}, "status": "v2_candidate", "v2_extensions": {extension: values[extension]}}


def _schema_probe_failures(schema: dict[str, Any]) -> list[str]:
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    failures: list[str] = []
    for extension in ("aoi", "acquisition", "algorithm_grounding", "quality_evidence", "delivery"):
        payload = _valid_envelope(extension)
        if list(validator.iter_errors(payload)) or semantic_failures(payload): failures.append(f"valid_{extension}_rejected")
    probes = {
        "missing_base_binding": _valid_envelope("aoi"), "resolved_aoi_without_hash": _valid_envelope("aoi"),
        "manual_preload_as_remote": _valid_envelope("acquisition"), "failed_attempt_without_code": _valid_envelope("acquisition"),
        "ambiguous_aoi_without_isolation": _valid_envelope("aoi"), "succeeded_without_materialization": _valid_envelope("acquisition"),
        "remote_succeeded_without_remote_success": _valid_envelope("acquisition"), "algorithm_partial_input": _valid_envelope("algorithm_grounding"),
        "lineage_source_mismatch": _valid_envelope("acquisition"), "single_source_with_two": _valid_envelope("quality_evidence"),
        "multi_source_with_one": _valid_envelope("quality_evidence"), "relaxed_hard_check": _valid_envelope("quality_evidence"),
        "gap_to_final": _valid_envelope("delivery"), "final_not_terminal": _valid_envelope("delivery"),
        "hard_failure_to_final": _valid_envelope("delivery"), "full_chain_missing_extensions": _valid_envelope("aoi"),
    }
    probes["missing_base_binding"].pop("base_template_sha256")
    probes["resolved_aoi_without_hash"]["v2_extensions"]["aoi"]["resolved_geometry_hash"] = None
    probes["ambiguous_aoi_without_isolation"]["v2_extensions"]["aoi"].update(resolution_status="ambiguous", resolved_geometry_hash=None, cross_aoi_isolation=False)
    probes["manual_preload_as_remote"]["v2_extensions"]["acquisition"][0].update(materialization_mode="manual_preload", manual_preload=True, remote_success=True)
    probes["failed_attempt_without_code"]["v2_extensions"]["acquisition"][0].update(attempt_status="failed", failure_code=None, artifact_hash=None)
    probes["succeeded_without_materialization"]["v2_extensions"]["acquisition"][0]["materialization_mode"] = "none"
    probes["remote_succeeded_without_remote_success"]["v2_extensions"]["acquisition"][0].update(materialization_mode="remote", remote_success=False)
    probes["algorithm_partial_input"]["lineage_binding"]["source_ids"].append("raw.gns.poi")
    probes["algorithm_partial_input"]["v2_extensions"]["algorithm_grounding"]["required_input_source_ids"].append("raw.gns.poi")
    probes["lineage_source_mismatch"]["lineage_binding"]["source_ids"] = ["raw.gns.poi"]
    probes["single_source_with_two"]["v2_extensions"]["quality_evidence"]["source_ids"].append("raw.gns.poi")
    probes["multi_source_with_one"]["v2_extensions"]["quality_evidence"].update(source_mode="multi_source", soft_adaptations=[])
    probes["relaxed_hard_check"]["v2_extensions"]["quality_evidence"]["hard_checks"][0]["relaxed"] = True
    probes["gap_to_final"]["v2_extensions"]["delivery"].update(from_state="gap", to_state="final")
    probes["final_not_terminal"]["v2_extensions"]["delivery"].update(from_state="provisional", to_state="final", terminal=False)
    quality = _valid_envelope("quality_evidence")["v2_extensions"]["quality_evidence"]
    quality.update(quality_gate_result="degraded", soft_adaptations=[]); quality["hard_checks"][0]["status"] = "fail"
    probes["hard_failure_to_final"]["v2_extensions"]["quality_evidence"] = quality
    probes["hard_failure_to_final"]["v2_extensions"]["delivery"].update(from_state="degraded", to_state="final", terminal=False)
    probes["full_chain_missing_extensions"]["base_template_id"] = "TF-EVIDENCE-COMPLETENESS"
    for name, payload in probes.items():
        if not list(validator.iter_errors(payload)) and not semantic_failures(payload): failures.append(f"invalid_probe_accepted:{name}")
    return failures


def audit(contract_path: Path, semantic_path: Path, schema_path: Path, matrix_path: Path, *, repo_root: Path | None = None) -> dict[str, Any]:
    root = (repo_root or contract_path.resolve().parents[2]).resolve()
    contracts, semantics = json.loads(contract_path.read_text(encoding="utf-8")), json.loads(semantic_path.read_text(encoding="utf-8"))
    schema, matrix = json.loads(schema_path.read_text(encoding="utf-8")), json.loads(matrix_path.read_text(encoding="utf-8"))
    failures: list[dict[str, Any]] = []
    try:
        bundle = load_frozen_design_bundle(str(root / "docs/current/benchmark/v1"), repo_root=str(root)); frozen_inputs_valid = True
    except Exception as error:
        bundle, frozen_inputs_valid = None, False; failures.append({"reason": "frozen_input_validation", "detail": str(error)})
    semantic_by_id = {item.get("family_id"): item for item in semantics.get("families", []) if isinstance(item, dict)}
    approved_ids = semantics.get("approved_family_ids", [])
    family_list = contracts.get("families", [])
    contract_ids = [item.get("template_family_id") for item in family_list if isinstance(item, dict)]
    if contract_ids != approved_ids or set(contract_ids) != set(semantic_by_id): failures.append({"reason": "contract_family_closure"})
    if contracts.get("source_manifest_sha256") != _sha256(semantic_path): failures.append({"reason": "source_manifest_hash_mismatch"})
    if contracts.get("kg_release_id") != semantics.get("kg_release_id") or contracts.get("partition") != "development": failures.append({"reason": "binding_or_partition_mismatch"})
    if contracts.get("evaluation_observation_points") != ["raw_plan", "pre_veto", "post_veto", "final_system_state"]: failures.append({"reason": "evaluation_observation_points"})
    tags: set[str] = set(); signatures: set[str] = set(); runtime_unverified: set[str] = set()
    if bundle:
        entities, policies = bundle.kg_entities, bundle.kg_policies
        registered_contracts = {item.get("contract_id") for item in _items(entities.get("product_contracts"))}
        registered_sources = {item.get("source_id") for item in _items(entities.get("data_sources"))}
        algorithms = {item.get("algo_id"): item for item in _items(entities.get("algorithms"))}
        registered_policies = _policy_ids(policies)
        roles = list(_items(policies.get("source_role_policies")))
        source_products = {product: {candidate.get("source_id") for role in roles if role.get("task_kind") == product and "Raster" not in role.get("geometry_types", []) for candidate in _items(role.get("candidates"))} for product in ALLOWED_PRODUCTS}
        bundles = {item.get("source_id"): set(item.get("component_candidates", [])) for item in _items(policies.get("source_bundle_policies"))}
    else: registered_contracts, registered_sources, algorithms, registered_policies, source_products, bundles = set(), set(), {}, set(), {}, {}
    for contract in family_list:
        if not isinstance(contract, dict): continue
        family_id, source = contract.get("template_family_id"), semantic_by_id.get(contract.get("template_family_id"), {})
        for field, semantic_field in (("status", "status"), ("product_types", "product_types"), ("complexity_level", "complexity")):
            if contract.get(field) != source.get(semantic_field): failures.append({"reason": "semantic_field_mismatch", "family_id": family_id, "field": field})
        for field in ("contract_ids", "source_ids", "algorithm_ids", "quality_policy_ids", "other_policy_ids", "chain_coverage", "required_v2_extensions"):
            if contract.get(field, []) != source.get(field, []): failures.append({"reason": "semantic_field_mismatch", "family_id": family_id, "field": field})
        if contract.get("oracle_summary") != source.get("oracle") or contract.get("veto_summary") != source.get("veto"): failures.append({"reason": "oracle_or_veto_mismatch", "family_id": family_id})
        if contract.get("chain_coverage") != EXPECTED_CHAIN.get(family_id): failures.append({"reason": "chain_coverage_overclaim", "family_id": family_id})
        if contract.get("required_v2_extensions", []) != EXPECTED_EXTENSIONS.get(family_id, []): failures.append({"reason": "v2_extension_mismatch", "family_id": family_id})
        if bool(contract.get("base_template_binding_required")) != (contract.get("status") == "v2_candidate"): failures.append({"reason": "base_template_binding", "family_id": family_id})
        eligibility = contract.get("e2e_eligibility"); expected_l4 = contract.get("complexity_level") == "L4"
        required_eligibility = {"eligible", "source_closed_required", "truth_or_quality_evaluable_required", "selection_independent_of_method_result"}
        if expected_l4 != isinstance(eligibility, dict) or (expected_l4 and (set(eligibility) != required_eligibility or not all(eligibility.values()))): failures.append({"reason": "l4_eligibility", "family_id": family_id})
        products = set(contract.get("product_types", [])); tags.update(contract.get("coverage_tags", []))
        if products - ALLOWED_PRODUCTS: failures.append({"reason": "product_scope", "family_id": family_id})
        family_text = json.dumps(source, ensure_ascii=False).lower()
        if "insar" in family_text or "raster" in family_text: failures.append({"reason": "forbidden_domain", "family_id": family_id})
        signature = json.dumps({key: contract.get(key) for key in ("product_types", "causal_variable_ids", "invariant_variable_ids", "nuisance_variable_ids", "oracle_summary", "veto_summary")}, sort_keys=True)
        if signature in signatures: failures.append({"reason": "semantic_copy", "family_id": family_id})
        signatures.add(signature)
        if not contract.get("historical_exclusion_checked") or not source.get("historical_exclusion"): failures.append({"reason": "historical_exclusion_unchecked", "family_id": family_id})
        if bundle:
            for identifier in contract.get("contract_ids", []):
                if identifier not in registered_contracts: failures.append({"reason": "unknown_contract", "family_id": family_id, "id": identifier})
                elif not any(f".{product}." in identifier for product in products): failures.append({"reason": "invalid_contract_product", "family_id": family_id, "id": identifier})
            for identifier in contract.get("source_ids", []):
                valid_raw = set().union(*(source_products.get(product, set()) for product in products))
                valid_catalogs = {catalog for catalog, members in bundles.items() if members & valid_raw}
                if identifier not in registered_sources: failures.append({"reason": "unknown_source", "family_id": family_id, "id": identifier})
                elif identifier not in valid_raw | valid_catalogs: failures.append({"reason": "invalid_source_role", "family_id": family_id, "id": identifier})
            for identifier in contract.get("algorithm_ids", []):
                algorithm = algorithms.get(identifier)
                if not algorithm or not (_algorithm_products(algorithm) & products): failures.append({"reason": "invalid_algorithm_product", "family_id": family_id, "id": identifier})
                elif algorithm.get("tool_ref") == "builtin:transform": runtime_unverified.add(identifier)
                elif algorithm.get("metadata", {}).get("selectable_now") is False: failures.append({"reason": "unselectable_algorithm", "family_id": family_id, "id": identifier})
            for identifier in contract.get("quality_policy_ids", []) + contract.get("other_policy_ids", []):
                if identifier not in registered_policies: failures.append({"reason": "unknown_policy", "family_id": family_id, "id": identifier})
                elif identifier.startswith("quality.default.") and not any(f".{product}." in identifier for product in products): failures.append({"reason": "invalid_quality_policy_product", "family_id": family_id, "id": identifier})
    if bundle:
        kg_check_ids = {item.get("check_id") for group in bundle.kg_policies.get("quality_check_templates", {}).values() for item in _items(group)}
        schema_check_ids = set(schema.get("$defs", {}).get("qualityEvidence", {}).get("properties", {}).get("hard_checks", {}).get("items", {}).get("properties", {}).get("check_id", {}).get("enum", []))
        if not schema_check_ids or not schema_check_ids.issubset(kg_check_ids): failures.append({"reason": "quality_check_crosswalk", "unknown": sorted(schema_check_ids - kg_check_ids)})
    if not REQUIRED_TAGS.issubset(tags): failures.append({"reason": "coverage_tags", "missing": sorted(REQUIRED_TAGS - tags)})
    evidence = next((item for item in family_list if item.get("template_family_id") == "TF-EVIDENCE-COMPLETENESS"), {})
    if set(evidence.get("source_ids", [])) != FIVE_PRODUCT_REQUIRED_SOURCES or set(evidence.get("chain_coverage", [])) != FULL_CHAIN: failures.append({"reason": "five_product_full_chain_closure"})
    try: schema_probe_failures = _schema_probe_failures(schema)
    except Exception as error: schema_probe_failures = [f"schema_invalid:{error}"]
    failures.extend({"reason": "schema_probe", "probe": item} for item in schema_probe_failures)
    matrix_ids = {item.get("template_family_id") for item in matrix.get("cells", []) if isinstance(item, dict)}
    expected_matrix_ids = {item.get("family_id") for item in semantics.get("families", []) if item.get("status") == "v2_candidate"}
    if matrix_ids != expected_matrix_ids or matrix.get("base_matrix_id") != "fusionagent.benchmark-capability-matrix.v1" or matrix.get("scope") != "extension_only" or matrix.get("status") != "v2_candidate" or matrix.get("kg_release_id") != semantics.get("kg_release_id"): failures.append({"reason": "matrix_candidate_closure"})
    inherited = set(bundle.matrix.get("capability_layers", [])) if bundle else set()
    if set(matrix.get("capability_layers_inherited", [])) != inherited or matrix.get("candidate_capability_layers_added") != []: failures.append({"reason": "matrix_layer_mapping"})
    if matrix.get("stage_to_capability_layer") != {"region": "planning", "delivery": "execution_evidence"}: failures.append({"reason": "matrix_stage_mapping"})
    if any(item.get("capability_layer") not in inherited for item in matrix.get("cells", [])): failures.append({"reason": "matrix_unknown_capability_layer"})
    if bundle:
        claim_ids = set(bundle.matrix.get("candidate_claim_ids", [])); gate_ids = {item.get("gate_id") for item in bundle.evaluation.get("gates", [])}
        for cell in matrix.get("cells", []):
            family = semantic_by_id.get(cell.get("template_family_id"), {})
            if cell.get("claim_id") not in claim_ids: failures.append({"reason": "matrix_unknown_claim", "cell_id": cell.get("capability_cell_id")})
            if cell.get("primary_gate") not in gate_ids or (cell.get("secondary_gate") and cell.get("secondary_gate") not in gate_ids): failures.append({"reason": "matrix_unknown_gate", "cell_id": cell.get("capability_cell_id")})
            if cell.get("complexity_level") != family.get("complexity"): failures.append({"reason": "matrix_complexity_mismatch", "cell_id": cell.get("capability_cell_id")})
            if bool(cell.get("e2e_eligibility")) != (cell.get("complexity_level") == "L4"): failures.append({"reason": "matrix_e2e_eligibility", "cell_id": cell.get("capability_cell_id")})
    delivery = next((item for item in matrix.get("cells", []) if item.get("template_family_id") == "TF-DELIVERY-STATE-TRACE"), {})
    if delivery.get("extends_capability_cell_id") != "BC-RECOVERY-03" or delivery.get("primary_gate") != "G6" or delivery.get("secondary_gate") != "G4": failures.append({"reason": "delivery_extension_mapping"})
    return {"audit_id": "fusionagent.method-selection-template-authoring-contract-audit.v2", "contract_manifest_id": contracts.get("contract_manifest_id"), "status": "passed_machine_only" if not failures else "failed", "family_count": len(family_list), "v2_matrix_cell_count": len(matrix.get("cells", [])), "frozen_inputs_valid": frozen_inputs_valid, "schema_probes_passed": not schema_probe_failures, "registered_runtime_unverified": sorted(runtime_unverified), "failures": failures, "independent_semantic_review_required": True, "development_only": contracts.get("partition") == "development", "provider_calls": 0, "judge_calls": 0, "instances_generated": 0}


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--contracts", type=Path, default=Path("docs/current/method-selection-template-authoring-contracts-v2-candidate.json")); parser.add_argument("--semantics", type=Path, default=Path("docs/current/method-selection-template-families-v2-candidate.json")); parser.add_argument("--schema", type=Path, default=Path("schemas/benchmark_template_v2_candidate_extension.schema.json")); parser.add_argument("--matrix", type=Path, default=Path("docs/current/benchmark/v2/capability_matrix_candidate.json")); parser.add_argument("--output", type=Path); args = parser.parse_args()
    result = audit(args.contracts, args.semantics, args.schema, args.matrix, repo_root=Path.cwd()); payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output: args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(payload, encoding="utf-8")
    print(json.dumps({"status": result["status"], "failure_count": len(result["failures"])}, ensure_ascii=False)); return 0 if result["status"] == "passed_machine_only" else 1


if __name__ == "__main__": raise SystemExit(main())
