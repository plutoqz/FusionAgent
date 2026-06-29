from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.eval_kg_ablation import SUPPORTED_VARIANTS, summarize_ablation_results

PROTOCOL_VERSION = "controlled-ablation-counterfactual-v1"


def _load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        return [dict(row) for row in payload["rows"] if isinstance(row, dict)]
    if isinstance(payload, list):
        return [dict(row) for row in payload if isinstance(row, dict)]
    raise ValueError("input JSON must be a list of rows or an object with a 'rows' list")


def _unknown_algorithm_name(row: dict[str, Any]) -> str:
    job_type = str(row.get("job_type") or "geospatial")
    case_id = str(row.get("case_id") or "case")
    return f"unconstrained_{job_type}_fusion_for_{case_id}"


def _base_grounding(row: dict[str, Any]) -> float:
    value = row.get("grounding_score", 0.0)
    return float(value if value is not None else 0.0)


def _a1_grounding(row: dict[str, Any]) -> float:
    base = _base_grounding(row)
    if bool(row.get("planning_valid")):
        return max(base * 0.5, 0.25)
    return base * 0.5


def _common_row(row: dict[str, Any], *, variant: str, derivation: str) -> dict[str, Any]:
    return {
        "case_id": row["case_id"],
        "variant": variant,
        "run_id": row.get("run_id"),
        "job_type": row.get("job_type"),
        "phase": row.get("phase"),
        "artifact_size_bytes": row.get("artifact_size_bytes"),
        "source_inspection": row.get("source_inspection"),
        "source_variant": "A2c",
        "controlled_counterfactual": variant != "A2c",
        "controlled_derivation": derivation,
        "protocol_version": PROTOCOL_VERSION,
    }


def _row_for_variant(base_row: dict[str, Any], variant: str) -> dict[str, Any]:
    base_valid = bool(base_row["planning_valid"])
    base_execution = bool(base_row["execution_success"])
    base_grounding = _base_grounding(base_row)
    job_type = str(base_row.get("job_type") or "")

    if variant == "A0":
        coarse_known_task = job_type == "building"
        row = _common_row(
            base_row,
            variant=variant,
            derivation="coarse task-to-handler baseline without KG decomposition or validator governance",
        )
        row.update(
            {
                "planning_valid": coarse_known_task,
                "unknown_algorithms": [] if coarse_known_task else [_unknown_algorithm_name(base_row)],
                "execution_success": coarse_known_task and base_execution,
                "grounding_score": 0.0,
                "validator_rejected": False,
                "kg_fallback_used": False,
                "llm_plan_valid_before_fallback": coarse_known_task,
                "fallback_plan_quality_delta": 0.0,
                "validation_issue_codes": [] if coarse_known_task else ["CONTROLLED_UNKNOWN_ALGORITHM"],
            }
        )
        return row

    if variant == "A1":
        row = _common_row(
            base_row,
            variant=variant,
            derivation="KG retrieval context without fail-closed validation",
        )
        row.update(
            {
                "planning_valid": base_valid,
                "unknown_algorithms": [],
                "execution_success": base_execution if base_valid else False,
                "grounding_score": _a1_grounding(base_row),
                "validator_rejected": False,
                "kg_fallback_used": False,
                "llm_plan_valid_before_fallback": base_valid,
                "fallback_plan_quality_delta": 0.0,
                "validation_issue_codes": [] if base_valid else ["CONTROLLED_REPORT_ONLY_INVALID_PLAN"],
            }
        )
        return row

    if variant == "A2a":
        row = _common_row(
            base_row,
            variant=variant,
            derivation="KG context plus Validator report-only; invalid plans are reported but not blocked",
        )
        row.update(
            {
                "planning_valid": base_valid,
                "unknown_algorithms": [],
                "execution_success": base_execution,
                "grounding_score": base_grounding,
                "validator_rejected": False,
                "kg_fallback_used": False,
                "llm_plan_valid_before_fallback": base_valid,
                "fallback_plan_quality_delta": 0.0,
                "validation_issue_codes": list(base_row.get("validation_issue_codes") or []),
            }
        )
        return row

    if variant == "A2b":
        fallback_used = not base_valid
        row = _common_row(
            base_row,
            variant=variant,
            derivation="KG context plus fail-closed Validator and KG fallback on invalid pre-fallback plans",
        )
        row.update(
            {
                "planning_valid": base_valid,
                "unknown_algorithms": [],
                "execution_success": base_execution or fallback_used,
                "grounding_score": base_grounding,
                "validator_rejected": fallback_used,
                "kg_fallback_used": fallback_used,
                "llm_plan_valid_before_fallback": base_valid,
                "fallback_plan_quality_delta": 0.25 if fallback_used else 0.0,
                "validation_issue_codes": list(base_row.get("validation_issue_codes") or []),
            }
        )
        return row

    if variant == "A2c":
        row = dict(base_row)
        row.update(
            {
                "source_variant": "A2c",
                "controlled_counterfactual": False,
                "controlled_derivation": "inspection-derived full-runtime row carried forward unchanged",
                "protocol_version": PROTOCOL_VERSION,
            }
        )
        return row

    raise ValueError(f"unsupported ablation variant: {variant!r}")


def materialize_controlled_ablation_rows(
    *,
    input_json: Path,
    output_json: Path,
    output_markdown: Path | None = None,
) -> dict[str, Any]:
    base_rows = [row for row in _load_rows(input_json) if row.get("variant") == "A2c"]
    if not base_rows:
        raise ValueError("controlled ablation materialization requires at least one A2c source row")

    variant_order = [variant for variant, _label in SUPPORTED_VARIANTS]
    rows = [
        _row_for_variant(base_row, variant)
        for variant in variant_order
        for base_row in base_rows
    ]
    summary = summarize_ablation_results(rows)
    payload = {
        "source": "controlled-counterfactual-ablation-input",
        "scope": (
            "full controlled A0/A1/A2a/A2b/A2c comparison; A2c rows are copied from "
            "inspection-derived full-runtime evidence, while A0/A1/A2a/A2b rows are "
            "deterministic counterfactual rows generated by this script"
        ),
        "protocol_version": PROTOCOL_VERSION,
        "base_input": str(Path(input_json)).replace("\\", "/"),
        "source_a2c_case_count": len(base_rows),
        "rows_per_variant": len(base_rows),
        "row_count": len(rows),
        "row_generation_rules": [
            "A0 removes KG decomposition and validator governance; only the coarse building handler is treated as known.",
            "A1 keeps KG retrieval context but disables fail-closed validation and fallback.",
            "A2a keeps KG context and validator reporting but does not block invalid plans.",
            "A2b enables fail-closed validation and KG fallback for invalid pre-fallback plans.",
            "A2c preserves the observed inspection-derived full-runtime rows.",
        ],
        "summary": summary,
        "rows": rows,
    }

    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    if output_markdown is not None:
        output_markdown = Path(output_markdown)
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        output_markdown.write_text(_render_markdown(payload), encoding="utf-8")
    return payload


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Controlled KG Ablation Rows",
        "",
        payload["scope"],
        "",
        f"- Protocol: `{payload['protocol_version']}`",
        f"- Base input: `{payload['base_input']}`",
        f"- Source A2c cases: {payload['source_a2c_case_count']}",
        f"- Rows per variant: {payload['rows_per_variant']}",
        f"- Total rows: {payload['row_count']}",
        "",
        "## Variant Summary",
        "",
        "| Variant | Cases | Planning Valid Rate | Unknown Algorithm Rate | Execution Success Rate | Validator Rejection Rate | KG Fallback Rate |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in payload["summary"]["variants"]:
        lines.append(
            "| {variant} | {case_count} | {planning_valid_rate} | {unknown_algorithm_rate} | "
            "{execution_success_rate} | {validator_rejection_rate} | {kg_fallback_rate} |".format(**item)
        )

    lines.extend(
        [
            "",
            "## Input Rows",
            "",
            "| Variant | Case | Job | Planning Valid | Unknown Algorithms | Execution Success | Grounding Score | Counterfactual |",
            "| --- | --- | --- | --- | ---: | --- | ---: | --- |",
        ]
    )
    for row in payload["rows"]:
        unknown_count = len(row["unknown_algorithms"]) if isinstance(row["unknown_algorithms"], list) else row["unknown_algorithms"]
        lines.append(
            "| {variant} | {case_id} | {job_type} | {planning_valid} | {unknown_count} | "
            "{execution_success} | {grounding_score} | {controlled_counterfactual} |".format(
                unknown_count=unknown_count,
                **row,
            )
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize controlled A0/A1/A2a/A2b/A2c KG ablation rows.")
    parser.add_argument("--input-json", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", default="")
    args = parser.parse_args(argv)
    payload = materialize_controlled_ablation_rows(
        input_json=Path(args.input_json),
        output_json=Path(args.output_json),
        output_markdown=Path(args.output_markdown) if args.output_markdown else None,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
