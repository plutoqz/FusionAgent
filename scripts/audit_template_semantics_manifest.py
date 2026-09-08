from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable


ALLOWED_PRODUCTS = {"building", "road", "water_polygon", "waterways", "poi"}
REQUIRED_CHAIN = {"region", "planning", "acquisition", "algorithm", "quality", "delivery"}
V2_REQUIRED_FIELDS = {
    "TF-AOI-RESOLUTION-BOUNDARY": "aoi",
    "TF-VECTOR-ACQUISITION-FAILURE": "acquisition",
    "TF-QUALITY-GATE-EVIDENCE": "quality_evidence",
    "TF-EVIDENCE-COMPLETENESS": "quality_evidence",
    "TF-DELIVERY-STATE-TRACE": "delivery",
}


def _items(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        return (item for item in value if isinstance(item, dict))
    return ()


def _registry_ids(entities: dict[str, Any], policies: dict[str, Any]) -> dict[str, set[str]]:
    registries: dict[str, set[str]] = {
        "contract": set(),
        "source": set(),
        "algorithm": set(),
        "quality_policy": set(),
        "policy": set(),
    }
    registries["contract"].update(item.get("contract_id") for item in _items(entities.get("product_contracts")))
    registries["source"].update(item.get("source_id") for item in _items(entities.get("data_sources")))
    registries["algorithm"].update(item.get("algo_id") for item in _items(entities.get("algorithms")))
    registries["quality_policy"].update(item.get("policy_id") for item in _items(policies.get("quality_policies")))
    for key, value in policies.items():
        if isinstance(value, dict) and isinstance(value.get("policy_id"), str):
            registries["policy"].add(value["policy_id"])
        for item in _items(value):
            if isinstance(item.get("policy_id"), str):
                registries["policy"].add(item["policy_id"])
    for values in registries.values():
        values.discard(None)
    return registries


def audit(manifest_path: Path, entities_path: Path, policies_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entities = json.loads(entities_path.read_text(encoding="utf-8"))
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    families = manifest.get("families", [])
    failures: list[dict[str, Any]] = []

    if manifest.get("status") != "v2_candidate_semantics_approved":
        failures.append({"reason": "invalid_manifest_status", "actual": manifest.get("status")})
    family_ids = [item.get("family_id") for item in families if isinstance(item, dict)]
    approved_ids = manifest.get("approved_family_ids", [])
    if family_ids != approved_ids or len(set(family_ids)) != len(family_ids):
        failures.append({"reason": "family_count_or_uniqueness", "count": len(families), "unique": len(set(family_ids))})
    products = {product for item in families if isinstance(item, dict) for product in item.get("product_types", [])}
    if products != ALLOWED_PRODUCTS:
        failures.append({"reason": "product_scope", "products": sorted(products)})
    chain = {stage for item in families if isinstance(item, dict) for stage in item.get("chain_coverage", [])}
    if not REQUIRED_CHAIN.issubset(chain):
        failures.append({"reason": "chain_coverage", "missing": sorted(REQUIRED_CHAIN - chain)})

    registries = _registry_ids(entities, policies)
    all_registered = set().union(*registries.values())
    unknown: list[dict[str, str]] = []
    for family in families:
        if not isinstance(family, dict):
            continue
        for field in ("contract_ids", "source_ids", "algorithm_ids", "quality_policy_ids", "other_policy_ids"):
            for identifier in family.get(field, []):
                if identifier not in all_registered:
                    unknown.append({"family_id": str(family.get("family_id")), "field": field, "id": str(identifier)})
    if unknown:
        failures.append({"reason": "unknown_kg_ids", "items": unknown})

    for family_id, field_name in V2_REQUIRED_FIELDS.items():
        family = next((item for item in families if item.get("family_id") == family_id), None)
        if not family or family.get("status") != "v2_candidate":
            failures.append({"reason": "missing_v2_candidate", "family_id": family_id})
        elif not manifest.get("v2_fields", {}).get(field_name):
            failures.append({"reason": "missing_v2_fields", "family_id": family_id, "field": field_name})

    acquisition = next((item for item in families if item.get("family_id") == "TF-VECTOR-ACQUISITION-FAILURE"), {})
    acquisition_text = json.dumps(acquisition, ensure_ascii=False)
    if "manual_preload" not in acquisition_text or "remote_success" not in acquisition_text:
        failures.append({"reason": "manual_preload_remote_success_semantics_missing"})
    return {
        "audit_id": "fusionagent.method-selection-template-semantics-audit.v1",
        "manifest_id": manifest.get("manifest_id"),
        "status": "passed" if not failures else "failed",
        "family_count": len(families),
        "products": sorted(products),
        "chain_coverage": sorted(chain),
        "registered_id_counts": {key: len(value) for key, value in registries.items()},
        "failures": failures,
        "user_template_review_required": True,
        "provider_calls": 0,
        "judge_calls": 0,
        "instances_generated": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("docs/current/method-selection-template-families-v2-candidate.json"))
    parser.add_argument("--entities", type=Path, default=Path("kg/ontology/v1.0.0/entities.json"))
    parser.add_argument("--policies", type=Path, default=Path("kg/ontology/v1.0.0/policies.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.manifest, args.entities, args.policies)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    print(json.dumps({"status": result["status"], "failure_count": len(result["failures"])}, ensure_ascii=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
