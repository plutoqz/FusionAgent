from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from benchmark_platform.canonical import canonical_sha256
from benchmark_platform.crosswalk import validate_crosswalk
from benchmark_platform.design_loader import load_frozen_design_bundle
from benchmark_platform.oracle import solve_template_oracle
from benchmark_platform.relations import resolve_json_path
from benchmark_platform.template_authoring import TemplateFamilyContract, audit_template_family
from benchmark_platform.template_registry import audit_template_registry
from benchmark_platform.template_v2 import semantic_failures, validate_v2_extension_document


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "docs/current/benchmark/v2/development_templates"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _family_cells(family_id: str, v1: dict[str, Any], v2: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    base = [item for item in v1.get("cells", []) if item.get("template_family_id") == family_id]
    candidate = [item for item in v2.get("cells", []) if item.get("template_family_id") == family_id]
    cells = base + candidate
    if not cells:
        raise ValueError(f"missing capability cell: {family_id}")
    unit_type = base[0]["experiment_unit_type"] if base else {"TF-ALGORITHM-CAPABILITY-GROUNDING": "counterfactual_pair", "TF-AOI-RESOLUTION-BOUNDARY": "counterfactual_pair", "TF-VECTOR-ACQUISITION-FAILURE": "temporal_trace", "TF-QUALITY-GATE-EVIDENCE": "counterfactual_pair", "TF-EVIDENCE-COMPLETENESS": "temporal_trace", "TF-DELIVERY-STATE-TRACE": "temporal_trace"}[family_id]
    return cells, unit_type


def _contract(family: dict[str, Any], authored: dict[str, Any], v1: dict[str, Any], v2: dict[str, Any]) -> TemplateFamilyContract:
    cells, unit_type = _family_cells(family["family_id"], v1, v2)
    return TemplateFamilyContract(
        template_family_id=family["family_id"],
        status=family["status"],
        product_types=tuple(family["product_types"]),
        complexity_level=authored["complexity_level"],
        claim_ids=tuple(dict.fromkeys(item["claim_id"] for item in cells)),
        capability_cell_ids=tuple(item["capability_cell_id"] for item in cells),
        mechanism_family=cells[-1]["mechanism_family"],
        experiment_unit_type=unit_type,
        coverage_tags=tuple(authored["coverage_tags"]),
        causal_variable_ids=tuple(authored["causal_variable_ids"]),
        invariant_variable_ids=tuple(authored["invariant_variable_ids"]),
        nuisance_variable_ids=tuple(authored["nuisance_variable_ids"]),
        contract_ids=tuple(authored["contract_ids"]),
        source_ids=tuple(authored["source_ids"]),
        algorithm_ids=tuple(authored["algorithm_ids"]),
        quality_policy_ids=tuple(authored["quality_policy_ids"]),
        other_policy_ids=tuple(authored["other_policy_ids"]),
        required_v2_extensions=tuple(authored["required_v2_extensions"]),
        historical_exclusion_checked=bool(authored["historical_exclusion_checked"]),
    )


def _check_variables(template: dict[str, Any], combined: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    for role in ("causal_variables", "invariants", "nuisance_variables"):
        for item in template.get("variables", {}).get(role, []):
            try:
                value = resolve_json_path(combined, item["json_path"])
            except Exception:
                failures.append(f"unresolved_variable_path:{item.get('variable_id')}")
                continue
            if value not in item.get("allowed_values", []):
                failures.append(f"current_value_outside_domain:{item.get('variable_id')}")
            if item.get("mutation_role") != {"causal_variables": "causal", "invariants": "invariant", "nuisance_variables": "nuisance"}[role]:
                failures.append(f"mutation_role_mismatch:{item.get('variable_id')}")
    return failures


def _check_crosswalk_sets(template: dict[str, Any], contract: TemplateFamilyContract) -> list[str]:
    refs = {str(item.get("reference_id")) for item in template.get("crosswalk", {}).get("references", []) if isinstance(item, dict)}
    expected = set(contract.contract_ids) | set(contract.source_ids) | set(contract.algorithm_ids)
    return ["crosswalk_contract_set_mismatch"] if not expected.issubset(refs) else []


def audit(package_root: Path = PACKAGE_ROOT) -> dict[str, Any]:
    semantics = _read(ROOT / "docs/current/method-selection-template-families-v2-candidate.json")
    authored_doc = _read(ROOT / "docs/current/method-selection-template-authoring-contracts-v2-candidate.json")
    v1_matrix = _read(ROOT / "docs/current/benchmark/v1/capability_matrix.json")
    v2_matrix = _read(ROOT / "docs/current/benchmark/v2/capability_matrix_candidate.json")
    schema = _read(ROOT / "schemas/benchmark_template_v2_candidate_extension.schema.json")
    manifest = _read(package_root / "authoring_manifest.json")
    bundle = load_frozen_design_bundle(str(ROOT / "docs/current/benchmark/v1"), repo_root=str(ROOT))
    families = {item["family_id"]: item for item in semantics["families"]}
    authored = {item["template_family_id"]: item for item in authored_doc["families"]}
    failures: list[dict[str, Any]] = []
    templates: list[dict[str, Any]] = []
    contracts: list[TemplateFamilyContract] = []
    details: list[dict[str, Any]] = []
    expected_ids = list(semantics["approved_family_ids"])
    if manifest.get("family_ids") != expected_ids or manifest.get("family_count") != len(expected_ids):
        failures.append({"reason": "manifest_family_closure"})
    for family_id in expected_ids:
        family = families[family_id]
        contract_data = authored[family_id]
        base_path = ROOT / manifest["entries"][expected_ids.index(family_id)]["base_template"]
        template = _read(base_path)
        contract = _contract(family, contract_data, v1_matrix, v2_matrix)
        contracts.append(contract)
        templates.append(template)
        local: list[str] = []
        try:
            from benchmark_platform.models import validate_template_document
            validate_template_document(template, bundle.schema_document)
        except Exception as error:
            local.append(f"v1_schema:{error}")
        try:
            validate_crosswalk(bundle, template)
        except Exception as error:
            local.append(f"crosswalk:{error}")
        try:
            result = audit_template_family(bundle, template, contract)
            if not result.passed:
                local.append("authoring_contract_not_passed")
        except Exception as error:
            local.append(f"authoring_contract:{error}")
        combined = dict(template)
        extension_path = package_root / "extensions" / f"{family_id}.json"
        extension = None
        if family["status"] == "v2_candidate":
            extension = _read(extension_path)
            combined.update(extension)
            try:
                validate_v2_extension_document(extension, schema)
            except Exception as error:
                local.append(f"v2_schema_or_semantics:{error}")
            if extension.get("base_template_sha256") != canonical_sha256(template):
                local.append("base_template_hash_mismatch")
            if extension.get("base_template_id") != family_id:
                local.append("base_template_id_mismatch")
            if set(extension.get("v2_extensions", {})) != set(contract.required_v2_extensions):
                local.append("v2_extension_set_mismatch")
            for extension_name in ("acquisition", "algorithm_grounding", "quality_evidence", "delivery"):
                values = extension.get("v2_extensions", {}).get(extension_name)
                if isinstance(values, list) and any(not item.get("task_id") for item in values if isinstance(item, dict)):
                    local.append(f"{extension_name}_task_binding_missing")
        local.extend(_check_variables(template, combined))
        local.extend(_check_crosswalk_sets(template, contract))
        try:
            proof = solve_template_oracle(template).model_dump(mode="json")
            proof_path = ROOT / manifest["entries"][expected_ids.index(family_id)]["oracle_proof"]
            if proof != _read(proof_path):
                local.append("oracle_proof_mismatch")
        except Exception as error:
            local.append(f"oracle:{error}")
        details.append({"template_family_id": family_id, "passed": not local, "failures": local})
        failures.extend({"reason": reason, "family_id": family_id} for reason in local)
    try:
        registry = audit_template_registry(tuple(contracts), tuple(templates))
        registry_payload = registry.model_dump(mode="json")
    except Exception as error:
        registry_payload = {"passed": False, "error": str(error)}
        failures.append({"reason": "registry", "detail": str(error)})
    report = {
        "audit_id": "fusionagent.method-selection-development-template-authoring-audit.v2-candidate",
        "status": "passed_authoring_spec_only" if not failures else "failed",
        "package_manifest": "docs/current/benchmark/v2/development_templates/authoring_manifest.json",
        "family_count": len(templates),
        "details": details,
        "registry": registry_payload,
        "provider_calls": 0,
        "judge_calls": 0,
        "instances_generated": 0,
        "formal_result_roots": 0,
        "generation_ready": False,
        "known_blocker": manifest.get("known_blocker"),
        "failures": failures,
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package-root", type=Path, default=PACKAGE_ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.package_root)
    output = args.output or args.package_root / "authoring_audit.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": report["status"], "failures": len(report["failures"]), "output": str(output)}, ensure_ascii=False))
    return 0 if report["status"].startswith("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
