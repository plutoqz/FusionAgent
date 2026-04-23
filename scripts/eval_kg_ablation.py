from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


SUPPORTED_VARIANTS: tuple[tuple[str, str], ...] = (
    ("kg_llm", "current full system"),
    ("kg_top_pattern", "KG skeleton fallback"),
    ("no_schema_hints", "removes data/source/parameter/schema hints"),
    ("no_kg_llm", "experimental baseline"),
)
REQUIRED_METRIC_FIELDS: tuple[str, ...] = (
    "planning_valid",
    "unknown_algorithms",
    "execution_success",
    "grounding_score",
)


def _rate(values: list[bool]) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if value) / len(values)


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _unknown_algorithm_count(value: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, bool):
        raise ValueError("unknown_algorithms must be a list or finite non-negative integer count")
    if isinstance(value, int):
        if value < 0:
            raise ValueError("unknown_algorithms must be a list or finite non-negative integer count")
        return value
    if isinstance(value, float):
        if not math.isfinite(value) or value < 0 or not value.is_integer():
            raise ValueError("unknown_algorithms must be a list or finite non-negative integer count")
        return int(value)
    raise ValueError("unknown_algorithms must be a list or finite non-negative integer count")


def _load_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict) and isinstance(payload.get("rows"), list):
        rows = payload["rows"]
    else:
        raise ValueError("input JSON must be a list of rows or an object with a 'rows' list")

    if not all(isinstance(row, dict) for row in rows):
        raise ValueError("every ablation row must be a JSON object")
    return rows


def summarize_ablation_results(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate supplied ablation rows without running live KG, API, or LLM calls."""
    supported_labels = dict(SUPPORTED_VARIANTS)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for index, row in enumerate(rows):
        variant = row.get("variant")
        if variant not in supported_labels:
            raise ValueError(f"unsupported ablation variant: {variant!r}")
        for field in REQUIRED_METRIC_FIELDS:
            if field not in row:
                raise ValueError(f"ablation row {index} is missing required metric field: {field}")
        _unknown_algorithm_count(row["unknown_algorithms"])
        grouped[str(variant)].append(row)

    variants: list[dict[str, Any]] = []
    for variant, label in SUPPORTED_VARIANTS:
        variant_rows = grouped.get(variant, [])
        if not variant_rows:
            variants.append(
                {
                    "variant": variant,
                    "label": label,
                    "status": "skipped",
                    "case_count": 0,
                    "planning_valid_rate": None,
                    "unknown_algorithm_rate": None,
                    "execution_success_rate": None,
                    "average_grounding_score": None,
                }
            )
            continue

        planning_values = [bool(row["planning_valid"]) for row in variant_rows]
        unknown_counts = [_unknown_algorithm_count(row["unknown_algorithms"]) for row in variant_rows]
        execution_values = [bool(row["execution_success"]) for row in variant_rows]
        grounding_values = [float(row["grounding_score"]) for row in variant_rows]

        variants.append(
            {
                "variant": variant,
                "label": label,
                "status": "evaluated",
                "case_count": len(variant_rows),
                "planning_valid_rate": _rate(planning_values),
                "unknown_algorithm_rate": _rate([count > 0 for count in unknown_counts]),
                "execution_success_rate": _rate(execution_values),
                "average_grounding_score": _average(grounding_values),
            }
        )

    return {
        "total_input_rows": len(rows),
        "supported_variants": [variant for variant, _label in SUPPORTED_VARIANTS],
        "variants": variants,
    }


def render_markdown_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# KG Ablation Summary",
        "",
        "This summary aggregates supplied rows only; it does not run live API, LLM, or KG calls.",
        "",
        "| Variant | Label | Status | Cases | Planning Valid Rate | Unknown Algorithm Rate | Execution Success Rate | Avg Grounding Score |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summary["variants"]:
        lines.append(
            "| {variant} | {label} | {status} | {case_count} | {planning_valid_rate} | "
            "{unknown_algorithm_rate} | {execution_success_rate} | {average_grounding_score} |".format(**item)
        )
    lines.append("")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Aggregate supplied KG ablation result rows.")
    parser.add_argument("--input-json", required=True, help="Input JSON list of rows or object with a 'rows' list.")
    parser.add_argument("--output-json", default="", help="Optional path to write aggregated summary JSON.")
    parser.add_argument("--output-markdown", default="", help="Optional path to write aggregated summary Markdown.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    rows = _load_rows(Path(args.input_json))
    summary = summarize_ablation_results(rows)
    output = json.dumps(summary, ensure_ascii=False, indent=2)
    print(output)

    if args.output_json:
        output_json = Path(args.output_json).resolve()
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(output, encoding="utf-8")

    if args.output_markdown:
        output_markdown = Path(args.output_markdown).resolve()
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        output_markdown.write_text(render_markdown_summary(summary), encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
