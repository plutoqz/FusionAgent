from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


VARIABLE_ROLES: dict[str, dict[str, list[str]]] = {
    "TF-CONTRACT-REQUIREDNESS": {"causal": ["VAR-CONTRACT-REQUIREDNESS"], "invariant": ["VAR-TASK-KIND", "VAR-OBSERVABLE-SOURCES"], "nuisance": []},
    "TF-WORDING-PARAPHRASE": {"causal": [], "invariant": ["VAR-CANONICAL-REQUEST", "VAR-OBSERVABLE-FACTS"], "nuisance": ["VAR-REQUEST-SURFACE-FORM"]},
    "TF-INPUT-ORDER": {"causal": [], "invariant": ["VAR-TASK-SET", "VAR-TASK-LOCAL-FACTS"], "nuisance": ["VAR-REQUEST-TASK-ORDER", "VAR-CONTEXT-RECORD-ORDER"]},
    "TF-IRRELEVANT-NOISE": {"causal": [], "invariant": ["VAR-REQUEST", "VAR-OBSERVABLE-FACTS"], "nuisance": ["VAR-IRRELEVANT-METADATA", "VAR-UNRELATED-CATALOG-ENTRY"]},
    "TF-CROSS-TASK-PRECEDENCE": {"causal": ["VAR-MISSION-PRIORITY"], "invariant": ["VAR-TASK-SET", "VAR-TASK-LOCAL-CONTRACTS"], "nuisance": []},
    "TF-KG-CROSSWALK-MISSING": {"causal": ["VAR-CROSSWALK-REFERENCE-EXISTS"], "invariant": ["VAR-REQUEST", "VAR-CONTRACT"], "nuisance": []},
    "TF-PLAN-STRUCTURE-INVALID": {"causal": ["VAR-PLAN-SCHEMA-VALID"], "invariant": ["VAR-PLANNER-INPUT", "VAR-OUTPUT-SCHEMA"], "nuisance": []},
    "TF-VALIDATOR-VETO": {"causal": ["VAR-CANDIDATE-PLAN-VETO-VIOLATION"], "invariant": ["VAR-REQUEST", "VAR-OBSERVABLE-FACTS", "VAR-CONTRACT"], "nuisance": []},
    "TF-ALGORITHM-CAPABILITY-GROUNDING": {"causal": ["VAR-ALGORITHM-TASK-COMPATIBILITY"], "invariant": ["VAR-CONTRACT", "VAR-SOURCE-SEMANTICS"], "nuisance": []},
    "TF-SOURCE-AVAILABILITY": {"causal": ["VAR-SOURCE-AVAILABILITY"], "invariant": ["VAR-TASK-KIND", "VAR-CONTRACT", "VAR-SOURCE-SEMANTICS"], "nuisance": []},
    "TF-AOI-RESOLUTION-BOUNDARY": {"causal": ["VAR-AOI-RESOLUTION-STATUS"], "invariant": ["VAR-TASK-SET", "VAR-KG-RELEASE"], "nuisance": ["VAR-AOI-SURFACE-FORM"]},
    "TF-VECTOR-ACQUISITION-FAILURE": {"causal": ["VAR-SOURCE-ATTEMPT-STATUS"], "invariant": ["VAR-AOI-GEOMETRY", "VAR-CONTRACT", "VAR-ALGORITHM"], "nuisance": ["VAR-RETRY-BUDGET"]},
    "TF-QUALITY-GATE-EVIDENCE": {"causal": ["VAR-QUALITY-GATE-ACCEPTED"], "invariant": ["VAR-CONTRACT", "VAR-HARD-CHECKS", "VAR-ARTIFACT-LINEAGE"], "nuisance": ["VAR-SOFT-ADAPTATION"]},
    "TF-EVIDENCE-COMPLETENESS": {"causal": ["VAR-REQUIRED-ARTIFACT-PRESENT"], "invariant": ["VAR-FROZEN-PLAN", "VAR-INPUT-HASHES", "VAR-CONTRACT"], "nuisance": ["VAR-EVIDENCE-ORDER"]},
    "TF-DELIVERY-STATE-TRACE": {"causal": ["VAR-LATEST-DELIVERY-STATE"], "invariant": ["VAR-CONTRACT", "VAR-SOURCE-STATE", "VAR-FAILURE-HISTORY"], "nuisance": ["VAR-EVIDENCE-ORDER"]},
}


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def build(manifest_path: Path) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    families = []
    for item in manifest["families"]:
        family_id = item["family_id"]
        roles = VARIABLE_ROLES[family_id]
        coverage_tags = list(item["coverage_tags"])
        # Registry tags are normalized indexes derived from the approved oracle/veto semantics.
        if "veto" not in coverage_tags:
            coverage_tags.append("veto")
        if "gap" in item["oracle"] and "gap" not in coverage_tags:
            coverage_tags.append("gap")
        e2e_eligibility = None
        if item["complexity"] == "L4":
            e2e_eligibility = {
                "eligible": True,
                "source_closed_required": True,
                "truth_or_quality_evaluable_required": True,
                "selection_independent_of_method_result": True,
            }
        families.append({
            "template_family_id": family_id,
            "status": item["status"],
            "product_types": item["product_types"],
            "complexity_level": item["complexity"],
            "coverage_tags": coverage_tags,
            "causal_variable_ids": roles["causal"],
            "invariant_variable_ids": roles["invariant"],
            "nuisance_variable_ids": roles["nuisance"],
            "contract_ids": item.get("contract_ids", []),
            "source_ids": item.get("source_ids", []),
            "algorithm_ids": item.get("algorithm_ids", []),
            "quality_policy_ids": item.get("quality_policy_ids", []),
            "other_policy_ids": item.get("other_policy_ids", []),
            "oracle_summary": item["oracle"],
            "veto_summary": item["veto"],
            "chain_coverage": item["chain_coverage"],
            "required_v2_fields": item.get("required_v2_fields", []),
            "required_v2_extensions": item.get("required_v2_extensions", []),
            "base_template_binding_required": item["status"] == "v2_candidate",
            "e2e_eligibility": e2e_eligibility,
            "historical_exclusion_checked": True,
        })
    return {
        "contract_manifest_id": "fusionagent.method-selection-template-authoring-contracts.v2-candidate",
        "status": "v2_candidate",
        "source_manifest": manifest["manifest_id"],
        "source_manifest_sha256": _sha256(manifest_path),
        "kg_release_id": manifest["kg_release_id"],
        "template_schema_id": "https://fusionagent.local/schemas/benchmark-template-v2-candidate-extension.json",
        "matrix_id": "fusionagent.benchmark-capability-matrix.v2-candidate",
        "partition": "development",
        "evaluation_observation_points": ["raw_plan", "pre_veto", "post_veto", "final_system_state"],
        "families": families,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("docs/current/method-selection-template-families-v2-candidate.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = build(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"family_count": len(result["families"]), "status": result["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
