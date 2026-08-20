from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote


AUDIT_ID = "fusionagent.benchmark-design-freeze-audit.v1"
DESIGN_ID = "fusionagent.benchmark-design.v1"
BASE_COMMIT = "8c5302f0b30ceccd353ca442bec40daa0a884b8b"
KG_RELEASE_ID = "fusionagent-kg-v1.0.0"
KG_SEMANTIC_HASH = "sha256:50067b9368914c47580707650789c04c78b2e856ccb3ef4d120a31f36c0ad71e"
CLAIM_IDS = {
    "CL-BENCH-CAUSAL",
    "CL-BENCH-INVARIANT",
    "CL-BENCH-COMPOSE",
    "CL-BENCH-RECOVERY",
    "CL-BENCH-DIAG",
}
CAPABILITY_LAYERS = {"kg", "projection", "planning", "validator", "execution_evidence"}
COMPLEXITY_LEVELS = {"L0", "L1", "L2", "L3", "L4"}
GATE_IDS = {f"G{index}" for index in range(7)}
PARTITION_IDS = {"development", "independent_confirmation", "selective_e2e"}
HISTORICAL_CASE_IDS = {*(f"C0{i}" for i in range(1, 7)), *(f"H0{i}" for i in range(1, 10))}
DESIGN_ASSETS = {
    "README.md",
    "benchmark_charter.md",
    "capability_matrix.json",
    "template.schema.json",
    "evaluation_contract.json",
    "human_review_rubric.md",
    "selection_governance.json",
    "protocol_review.json",
    "freeze_manifest.json",
}
EXPECTED_MANIFEST_FILES = {
    "docs/current/benchmark/v1/README.md",
    "docs/current/benchmark/v1/benchmark_charter.md",
    "docs/current/benchmark/v1/capability_matrix.json",
    "docs/current/benchmark/v1/template.schema.json",
    "docs/current/benchmark/v1/evaluation_contract.json",
    "docs/current/benchmark/v1/human_review_rubric.md",
    "docs/current/benchmark/v1/selection_governance.json",
    "docs/current/benchmark/v1/protocol_review.json",
    "scripts/audit_benchmark_design_freeze.py",
    "tests/test_benchmark_design_freeze.py",
}
AUTHORITATIVE_INPUT_HASHES = {
    "docs/current/research-charter.md": "sha256:223d3ca0719a69c373a4e6a95853c1c55b23a18ae5cef40eb1267fe10c855207",
    "docs/current/research-claim-evidence-ledger.md": "sha256:afa05fcb8e496c8bda528837e50d86b8f942eaa93967b59f59580a0443e282ef",
    "docs/current/research-experiment-ledger.md": "sha256:a1f859e306701cc2293287168c29d70254800a05ecf9bfe166419d1f4f50ec14",
    "docs/current/research-governance-index.md": "sha256:f1080d9961a6cab16e21f85e4b5b04bd9458d9eca1a4336522f8aea4045d06d6",
    "kg/ontology/v1.0.0/release.json": "sha256:8d0d801331a4c57b062442f2b7cc9b836de207ee3792d0de2db75b65bbbeb35b",
}
ALLOWED_CHANGED_PREFIXES = (
    "docs/current/benchmark/v1/",
    "scripts/audit_benchmark_design_freeze.py",
    "tests/test_benchmark_design_freeze.py",
    "docs/README.md",
    "docs/current/research-governance-index.md",
    "docs/current/research-experiment-ledger.md",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def sha256_manifest_file(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def local_schema_refs(schema: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(schema, dict):
        for key, value in schema.items():
            if key == "$ref" and isinstance(value, str) and value.startswith("#/$defs/"):
                refs.add(value.removeprefix("#/$defs/"))
            else:
                refs.update(local_schema_refs(value))
    elif isinstance(schema, list):
        for value in schema:
            refs.update(local_schema_refs(value))
    return refs


def open_object_schema_paths(schema: Any, path: str = "$") -> list[str]:
    failures: list[str] = []
    if isinstance(schema, dict):
        if schema.get("type") == "object" and schema.get("additionalProperties") is not False:
            failures.append(path)
        for key, value in schema.items():
            failures.extend(open_object_schema_paths(value, f"{path}.{key}"))
    elif isinstance(schema, list):
        for index, value in enumerate(schema):
            failures.extend(open_object_schema_paths(value, f"{path}[{index}]"))
    return failures


def root_key_errors(schema: dict[str, Any], instance: dict[str, Any]) -> dict[str, list[str]]:
    properties = set(schema.get("properties", {}))
    required = set(schema.get("required", []))
    keys = set(instance)
    return {
        "unknown": sorted(keys - properties) if schema.get("additionalProperties") is False else [],
        "missing": sorted(required - keys),
    }


def manifest_hash_errors(root: Path, manifest: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for item in manifest.get("files", []):
        relative_path = item.get("path")
        expected = item.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(expected, str):
            errors.append({"path": str(relative_path), "error": "invalid manifest entry"})
            continue
        path = root / relative_path
        if not path.is_file():
            errors.append({"path": relative_path, "error": "missing"})
            continue
        actual = sha256_manifest_file(path)
        if actual != expected:
            errors.append({"path": relative_path, "error": "hash mismatch", "expected": expected, "actual": actual})
    return errors


def manifest_file_map(manifest: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    file_map: dict[str, str] = {}
    duplicates: list[str] = []
    for item in manifest.get("files", []):
        path = item.get("path")
        digest = item.get("sha256")
        if not isinstance(path, str) or not isinstance(digest, str):
            continue
        if path in file_map:
            duplicates.append(path)
        file_map[path] = digest
    return file_map, sorted(set(duplicates))


def local_markdown_link_errors(markdown_paths: Iterable[Path]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    link_pattern = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    for markdown_path in markdown_paths:
        for raw_target in link_pattern.findall(markdown_path.read_text(encoding="utf-8")):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            decoded_path = unquote(target.split("#", 1)[0])
            resolved = (markdown_path.parent / decoded_path).resolve()
            if not resolved.exists():
                errors.append({"file": markdown_path.as_posix(), "target": raw_target})
    return errors


def milestone_state_matches_review(manifest: dict[str, Any], review: dict[str, Any]) -> bool:
    milestone = manifest.get("milestone", {})
    review_approved = (
        review.get("status") == "approved"
        and review.get("decision") == "approved"
        and review.get("reviewer", {}).get("role") in {"user", "independent_reviewer"}
        and review.get("reviewer", {}).get("independent_of_authoring") is True
        and review.get("checklist")
        and all(item.get("decision") == "approved" for item in review["checklist"])
    )
    if review_approved:
        return (
            milestone.get("status") == "complete"
            and milestone.get("complete") is True
            and milestone.get("blocking_gate") is None
        )
    return (
        milestone.get("status") == "blocked_before_freeze"
        and milestone.get("complete") is False
        and milestone.get("blocking_gate") == "human_protocol_review"
    )


def failure_class_mapping_errors(cells: Iterable[dict[str, Any]], gates: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    failure_classes_by_gate = {
        str(gate.get("gate_id")): {str(value) for value in gate.get("failure_classes", [])}
        for gate in gates
    }
    errors: list[dict[str, str]] = []
    for cell in cells:
        gate_id = str(cell.get("primary_gate"))
        failure_class = str(cell.get("primary_failure_class"))
        if failure_class not in failure_classes_by_gate.get(gate_id, set()):
            errors.append(
                {
                    "capability_cell_id": str(cell.get("capability_cell_id")),
                    "primary_gate": gate_id,
                    "primary_failure_class": failure_class,
                }
            )
    return errors


def _git_lines(repo_root: Path, *args: str) -> list[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return [line.strip().replace("\\", "/") for line in completed.stdout.splitlines() if line.strip()]


def changed_paths(repo_root: Path) -> list[str]:
    committed = _git_lines(repo_root, "diff", "--name-only", BASE_COMMIT, "HEAD")
    unstaged = _git_lines(repo_root, "diff", "--name-only")
    staged = _git_lines(repo_root, "diff", "--cached", "--name-only")
    untracked = _git_lines(repo_root, "ls-files", "--others", "--exclude-standard")
    return sorted(set([*committed, *unstaged, *staged, *untracked]))


def _allowed_changed_path(path: str) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in ALLOWED_CHANGED_PREFIXES)


def _check(checks: list[dict[str, Any]], check_id: str, passed: bool, details: Any, *, required: bool = True) -> None:
    checks.append({"check_id": check_id, "required": required, "passed": bool(passed), "details": details})


def audit_design(repo_root: Path, design_root: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    missing_files = sorted(name for name in DESIGN_ASSETS if not (design_root / name).is_file())
    _check(checks, "required_design_files", not missing_files, {"missing": missing_files})

    matrix = load_json(design_root / "capability_matrix.json")
    schema = load_json(design_root / "template.schema.json")
    evaluation = load_json(design_root / "evaluation_contract.json")
    selection = load_json(design_root / "selection_governance.json")
    review = load_json(design_root / "protocol_review.json")
    manifest = load_json(design_root / "freeze_manifest.json")
    charter_text = (design_root / "benchmark_charter.md").read_text(encoding="utf-8")
    rubric_text = (design_root / "human_review_rubric.md").read_text(encoding="utf-8")

    expected_ids = {
        "matrix": "fusionagent.benchmark-capability-matrix.v1",
        "evaluation": "fusionagent.benchmark-evaluation-contract.v1",
        "selection": "fusionagent.benchmark-selection-governance.v1",
        "manifest": "fusionagent.benchmark-design-freeze.v1",
    }
    actual_ids = {
        "matrix": matrix.get("matrix_id"),
        "evaluation": evaluation.get("evaluation_contract_id"),
        "selection": selection.get("selection_governance_id"),
        "manifest": manifest.get("freeze_id"),
    }
    _check(checks, "asset_identities", actual_ids == expected_ids, {"expected": expected_ids, "actual": actual_ids})

    manifest_files, duplicate_manifest_paths = manifest_file_map(manifest)
    manifest_inputs = {
        item.get("path"): item.get("sha256")
        for item in manifest.get("authoritative_inputs", [])
        if isinstance(item, dict) and isinstance(item.get("path"), str)
    }
    manifest_accounting = manifest.get("zero_call_accounting", {})
    manifest_integrity = manifest.get("integrity_assertions", {})
    manifest_git = manifest.get("git", {})
    manifest_kg = manifest.get("kg_release", {})
    manifest_contract_details = {
        "file_paths": sorted(manifest_files),
        "missing_file_paths": sorted(EXPECTED_MANIFEST_FILES - set(manifest_files)),
        "unexpected_file_paths": sorted(set(manifest_files) - EXPECTED_MANIFEST_FILES),
        "duplicate_file_paths": duplicate_manifest_paths,
        "authoritative_inputs": manifest_inputs,
        "zero_call_accounting": manifest_accounting,
        "integrity_assertions": manifest_integrity,
    }
    manifest_contract_pass = (
        set(manifest_files) == EXPECTED_MANIFEST_FILES
        and not duplicate_manifest_paths
        and manifest_inputs == AUTHORITATIVE_INPUT_HASHES
        and manifest_git.get("base_commit") == BASE_COMMIT
        and manifest_git.get("branch") == "codex/benchmark-design-r1"
        and manifest_kg.get("release_id") == KG_RELEASE_ID
        and manifest_kg.get("semantic_hash") == KG_SEMANTIC_HASH
        and manifest_kg.get("file_sha256") == AUTHORITATIVE_INPUT_HASHES["kg/ontology/v1.0.0/release.json"]
        and manifest_kg.get("changed") is False
        and manifest_accounting
        == {
            "instances_generated": 0,
            "provider_call_count": 0,
            "judge_call_count": 0,
            "formal_result_root_count": 0,
        }
        and manifest_integrity.get("historical_evidence_mutated") is False
        and manifest_integrity.get("kg_release_changed") is False
        and manifest.get("file_hash_canonicalization") == "normalize_crlf_to_lf"
        and isinstance(manifest.get("audit_generated_at"), str)
    )
    _check(checks, "freeze_manifest_contract", manifest_contract_pass, manifest_contract_details)

    cells = matrix.get("cells", [])
    cell_ids = [cell.get("capability_cell_id") for cell in cells]
    claim_ids = {cell.get("claim_id") for cell in cells}
    mechanism_counts: dict[str, set[str]] = defaultdict(set)
    for cell in cells:
        mechanism_counts[str(cell.get("claim_id"))].add(str(cell.get("mechanism_family")))
    matrix_details = {
        "cell_count": len(cells),
        "unique_cell_count": len(set(cell_ids)),
        "claim_ids": sorted(str(value) for value in claim_ids),
        "mechanisms_per_claim": {key: len(value) for key, value in sorted(mechanism_counts.items())},
        "capability_layers": sorted({cell.get("capability_layer") for cell in cells}),
        "complexity_levels": sorted({cell.get("complexity_level") for cell in cells}),
    }
    matrix_pass = (
        len(cells) == matrix.get("acceptance", {}).get("expected_cell_count") == 17
        and len(set(cell_ids)) == len(cell_ids)
        and claim_ids == CLAIM_IDS
        and all(len(mechanism_counts[claim_id]) >= 2 for claim_id in CLAIM_IDS)
        and {cell.get("capability_layer") for cell in cells} == CAPABILITY_LAYERS
        and {cell.get("complexity_level") for cell in cells} == COMPLEXITY_LEVELS
    )
    _check(checks, "capability_matrix_coverage", matrix_pass, matrix_details)

    matrix_exclusions = set(matrix.get("historical_exclusions", {}).get("case_ids", []))
    selection_exclusions = set(selection.get("historical_exclusion", {}).get("case_ids", []))
    charter_exclusions = {case_id for case_id in HISTORICAL_CASE_IDS if case_id in charter_text}
    _check(
        checks,
        "historical_case_exclusion",
        matrix_exclusions == selection_exclusions == charter_exclusions == HISTORICAL_CASE_IDS,
        {
            "matrix": sorted(matrix_exclusions),
            "selection": sorted(selection_exclusions),
            "charter": sorted(charter_exclusions),
        },
    )

    defs = set(schema.get("$defs", {}))
    refs = local_schema_refs(schema)
    open_objects = open_object_schema_paths(schema)
    top_errors = root_key_errors(schema, {"unexpected": True})
    schema_details = {
        "draft": schema.get("$schema"),
        "definition_count": len(defs),
        "local_refs": sorted(refs),
        "missing_refs": sorted(refs - defs),
        "open_object_paths": open_objects,
        "unknown_root_key_rejected": top_errors["unknown"] == ["unexpected"],
        "maximum_causal_mutations_per_pair": schema.get("$defs", {}).get("variables", {}).get("properties", {}).get("maximum_causal_mutations_per_pair", {}).get("const"),
    }
    schema_pass = (
        schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
        and schema.get("additionalProperties") is False
        and not (refs - defs)
        and not open_objects
        and top_errors["unknown"] == ["unexpected"]
        and schema_details["maximum_causal_mutations_per_pair"] == 1
    )
    _check(checks, "template_schema_contract", schema_pass, schema_details)

    gate_ids = {gate.get("gate_id") for gate in evaluation.get("gates", [])}
    referenced_gates = {cell.get("primary_gate") for cell in cells}
    failure_mapping_errors = failure_class_mapping_errors(cells, evaluation.get("gates", []))
    rate_metrics = [
        metric
        for metric in evaluation.get("metrics", [])
        if any(token in str(metric.get("metric_id")) for token in ("rate", "accuracy", "coverage"))
    ]
    missing_denominators = [metric.get("metric_id") for metric in rate_metrics if not metric.get("denominator")]
    evaluation_details = {
        "gate_ids": sorted(str(value) for value in gate_ids),
        "missing_matrix_gates": sorted(str(value) for value in referenced_gates - gate_ids),
        "failure_class_mapping_errors": failure_mapping_errors,
        "metric_count": len(evaluation.get("metrics", [])),
        "rate_metric_count": len(rate_metrics),
        "missing_denominators": missing_denominators,
        "overall_composite_score": evaluation.get("aggregation", {}).get("overall_composite_score"),
    }
    evaluation_pass = (
        gate_ids == GATE_IDS
        and not (referenced_gates - gate_ids)
        and not failure_mapping_errors
        and not missing_denominators
        and evaluation.get("aggregation", {}).get("overall_composite_score") == "forbidden"
        and evaluation.get("human_review", {}).get("llm_judge_formal_truth_allowed") is False
    )
    _check(checks, "evaluation_contract_coverage", evaluation_pass, evaluation_details)

    rubric_tokens = {
        "Reviewer A",
        "Reviewer B",
        "Adjudicator",
        "unscorable",
        "pending_human_review",
        "LLM judge",
        "HR-CONTRACT-SEMANTICS",
        "HR-TASK-LOCALITY",
        "HR-RECOVERY-HISTORY",
        "HR-EVIDENCE-SUFFICIENCY",
    }
    missing_rubric_tokens = sorted(token for token in rubric_tokens if token not in rubric_text)
    _check(checks, "human_rubric_completeness", not missing_rubric_tokens, {"missing_tokens": missing_rubric_tokens})

    partitions = selection.get("partitions", [])
    partition_ids = {partition.get("partition_id") for partition in partitions}
    seeds = [partition.get("master_seed") for partition in partitions]
    forbidden_exclusions_enabled = [
        rule.get("rule_id")
        for rule in selection.get("exclusion_rules", [])
        if rule.get("rule_id") in {"EX-METHOD-PERFORMANCE", "EX-HUMAN-DISAGREEMENT"} and rule.get("allowed") is not False
    ]
    accounting = selection.get("current_design_freeze_accounting", {})
    selection_details = {
        "partition_ids": sorted(str(value) for value in partition_ids),
        "unique_seed_count": len(set(seeds)),
        "forbidden_exclusions_enabled": forbidden_exclusions_enabled,
        "accounting": accounting,
    }
    selection_pass = (
        partition_ids == PARTITION_IDS
        and len(set(seeds)) == len(partitions) == 3
        and not forbidden_exclusions_enabled
        and accounting.get("instances_generated") == 0
        and accounting.get("provider_calls") == 0
        and accounting.get("judge_calls") == 0
        and accounting.get("formal_result_roots_created") == 0
        and accounting.get("confirmation_unsealed") is False
    )
    _check(checks, "selection_governance", selection_pass, selection_details)

    manifest_errors = manifest_hash_errors(repo_root, manifest)
    _check(checks, "freeze_manifest_hashes", not manifest_errors, {"errors": manifest_errors, "file_count": len(manifest.get("files", []))})

    expected_design_inventory = DESIGN_ASSETS | {"freeze_audit.json"}
    actual_design_inventory = {path.name for path in design_root.iterdir() if path.is_file()}
    unexpected_design_files = sorted(actual_design_inventory - expected_design_inventory)
    nested_design_paths = sorted(path.relative_to(design_root).as_posix() for path in design_root.rglob("*") if path.is_dir())
    _check(
        checks,
        "design_directory_inventory",
        not unexpected_design_files and not nested_design_paths,
        {
            "files": sorted(actual_design_inventory),
            "unexpected_files": unexpected_design_files,
            "nested_directories": nested_design_paths,
        },
    )

    markdown_paths = sorted(design_root.glob("*.md"))
    markdown_link_errors = local_markdown_link_errors(markdown_paths)
    _check(checks, "markdown_links", not markdown_link_errors, {"errors": markdown_link_errors})

    kg_release_path = repo_root / "kg" / "ontology" / "v1.0.0" / "release.json"
    kg_release = load_json(kg_release_path)
    kg_details = {
        "release_id": kg_release.get("release_id"),
        "semantic_hash": kg_release.get("semantic_hash"),
        "file_sha256": sha256_file(kg_release_path),
    }
    _check(
        checks,
        "kg_release_unchanged",
        kg_release.get("release_id") == KG_RELEASE_ID
        and kg_release.get("semantic_hash") == KG_SEMANTIC_HASH
        and kg_details["file_sha256"] == "sha256:8d0d801331a4c57b062442f2b7cc9b836de207ee3792d0de2db75b65bbbeb35b",
        kg_details,
    )

    paths = changed_paths(repo_root)
    forbidden_paths = [path for path in paths if not _allowed_changed_path(path)]
    historical_mutations = [
        path
        for path in paths
        if path.startswith(("kg/", "docs/current/evidence/", "docs/current/research-case-manifest", "services/", "schemas/", "llm/"))
    ]
    _check(
        checks,
        "bounded_change_set",
        not forbidden_paths and not historical_mutations,
        {"changed_paths": paths, "forbidden_paths": forbidden_paths, "historical_mutations": historical_mutations},
    )

    review_items = review.get("checklist", [])
    review_pass = (
        review.get("status") == "approved"
        and review.get("decision") == "approved"
        and review.get("reviewer", {}).get("role") in {"user", "independent_reviewer"}
        and review.get("reviewer", {}).get("independent_of_authoring") is True
        and review_items
        and all(item.get("decision") == "approved" for item in review_items)
    )
    _check(
        checks,
        "human_protocol_review",
        review_pass,
        {
            "status": review.get("status"),
            "decision": review.get("decision"),
            "reviewer": review.get("reviewer"),
            "pending_items": [item.get("item_id") for item in review_items if item.get("decision") != "approved"],
        },
    )
    _check(
        checks,
        "milestone_state_consistency",
        milestone_state_matches_review(manifest, review),
        {"milestone": manifest.get("milestone"), "review_status": review.get("status"), "review_decision": review.get("decision")},
    )

    required_failures = [check["check_id"] for check in checks if check["required"] and not check["passed"]]
    return {
        "audit_id": AUDIT_ID,
        "design_id": DESIGN_ID,
        "generated_at": manifest.get("audit_generated_at"),
        "repo_root": str(repo_root),
        "design_root": str(design_root),
        "base_commit": BASE_COMMIT,
        "checks": checks,
        "required_check_count": sum(1 for check in checks if check["required"]),
        "passed_required_check_count": sum(1 for check in checks if check["required"] and check["passed"]),
        "required_failures": required_failures,
        "overall_passed": not required_failures,
        "milestone_status": "complete" if not required_failures else "blocked_before_freeze",
        "accounting": {
            "instances_generated": 0,
            "provider_calls": 0,
            "judge_calls": 0,
            "formal_result_roots_created": 0,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit the zero-call FusionAgent benchmark design freeze.")
    parser.add_argument("--root", required=True, type=Path, help="Benchmark design root relative to or inside the repository.")
    parser.add_argument("--output", required=True, type=Path, help="Audit JSON output path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    design_root = args.root if args.root.is_absolute() else repo_root / args.root
    output = args.output if args.output.is_absolute() else repo_root / args.output
    result = audit_design(repo_root.resolve(), design_root.resolve())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"overall_passed": result["overall_passed"], "required_failures": result["required_failures"]}))
    return 0 if result["overall_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
