"""Create a post-hoc decomposition without changing confirmatory outcomes."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from kg.knowledge_release import sha256_file
from schemas.research_llm_pilot import ResearchPlanningDecision
from scripts import run_simplified_kg_experiment as experiment


METRICS = (
    "schema_valid",
    "decision_accepted",
    "canonical_order",
    "semantic_delivery",
    "evidence_complete",
    "oracle_pass",
)


def _row_metrics(row: dict[str, Any]) -> dict[str, bool]:
    plan_payload = row.get("plan")
    plan = ResearchPlanningDecision.model_validate(plan_payload) if plan_payload else None
    oracle = row["oracle"]
    tasks = [item.task_kind for item in plan.tasks] if plan else []
    states = {item.task_kind: item.delivery_state for item in plan.tasks} if plan else {}
    text = " ".join(
        [
            *(plan.evidence if plan else []),
            *(plan.uncertainties if plan else []),
            *((item.rationale for item in plan.tasks) if plan else []),
        ]
    ).casefold()
    anchors = list(oracle["ground_truth"].get("evidence_anchors") or [])
    return {
        "schema_valid": bool(plan is not None and not row.get("error")),
        "decision_accepted": bool(plan and plan.decision in oracle["acceptance"]["allowed_decisions"]),
        "canonical_order": tasks == oracle["ground_truth"]["canonical_order"],
        "semantic_delivery": experiment._matches_v3_delivery(
            row,
            plan,
            actual_tasks=tasks,
            actual_states=states,
        ),
        "evidence_complete": bool(plan and plan.evidence) and all(
            str(anchor).casefold() in text for anchor in anchors
        ),
        "oracle_pass": bool(row["oracle_pass"]),
    }


def analyze(rows: list[dict[str, Any]]) -> dict[str, Any]:
    raw: dict[tuple[str, str], list[tuple[dict[str, Any], dict[str, bool]]]] = defaultdict(list)
    for row in rows:
        raw[(str(row["method"]), str(row["case_id"]))].append((row, _row_metrics(row)))

    cases: list[dict[str, Any]] = []
    for (method, case_id), items in raw.items():
        first = items[0][0]
        cases.append(
            {
                "method": method,
                "case_id": case_id,
                "family": first["family"],
                "variant": first["variant"],
                **{
                    metric: experiment._majority(values[metric] for _row, values in items)
                    for metric in METRICS
                },
            }
        )

    methods = []
    for method in experiment.PRIMARY_METHODS:
        case_group = [item for item in cases if item["method"] == method]
        fault = [item for item in case_group if item["variant"] == "fault"]
        execution_group = [row for row in rows if row["method"] == method]
        methods.append(
            {
                "method": method,
                "case_count": len(case_group),
                "execution_count": len(execution_group),
                "execution_schema_valid_rate": experiment._rate(
                    [not row.get("error") and row.get("plan") is not None for row in execution_group]
                ),
                **{
                    f"fault_{metric}_rate": experiment._rate([item[metric] for item in fault])
                    for metric in METRICS
                },
                **{
                    f"fault_{metric}_count": sum(bool(item[metric]) for item in fault)
                    for metric in METRICS
                },
                "fault_denominator": len(fault),
            }
        )

    semantic_maps = {
        method: {
            item["case_id"]: {**item, "oracle_pass": item["semantic_delivery"]}
            for item in cases
            if item["method"] == method and item["variant"] == "fault"
        }
        for method in experiment.PRIMARY_METHODS
    }
    full = semantic_maps["llm_full_contract_kg"]
    comparisons = []
    for comparator_name in ("llm_only", "llm_capability_kg", "rules_only", "fixed_workflow"):
        comparator = semantic_maps[comparator_name]
        shared = sorted(set(full) & set(comparator))
        full_only = sum(full[item]["oracle_pass"] and not comparator[item]["oracle_pass"] for item in shared)
        comparator_only = sum(comparator[item]["oracle_pass"] and not full[item]["oracle_pass"] for item in shared)
        difference = (
            sum(bool(full[item]["oracle_pass"]) for item in shared)
            - sum(bool(comparator[item]["oracle_pass"]) for item in shared)
        ) / len(shared)
        comparisons.append(
            {
                "comparator": comparator_name,
                "difference_vs_full_kg": difference,
                "full_kg_only_pass": full_only,
                "comparator_only_pass": comparator_only,
                "mcnemar_exact_p": experiment._mcnemar_exact_p(full_only, comparator_only),
                "scenario_cluster_bootstrap_95": experiment._cluster_bootstrap_difference(full, comparator),
            }
        )
    scenario_results = []
    for family in sorted({item["family"] for item in cases if item["variant"] == "fault"}):
        entry: dict[str, Any] = {"scenario": family}
        for method in experiment.PRIMARY_METHODS:
            group = [
                item for item in cases
                if item["method"] == method and item["variant"] == "fault" and item["family"] == family
            ]
            entry[method] = {
                "semantic_delivery_count": sum(item["semantic_delivery"] for item in group),
                "oracle_pass_count": sum(item["oracle_pass"] for item in group),
                "total": len(group),
            }
        scenario_results.append(entry)
    return {
        "status": "post_hoc_diagnostic_not_primary_confirmatory_endpoint",
        "analysis_unit": "case-level majority across exact-input replicates",
        "methods": methods,
        "semantic_delivery_paired_comparisons": comparisons,
        "scenario_results": scenario_results,
    }


def render(report: dict[str, Any]) -> str:
    lines = [
        "# Held-out Diagnostic Decomposition",
        "",
        "This is a post-hoc diagnostic. It does not replace the predeclared primary oracle pass and does not retroactively change case acceptance.",
        "",
        "`semantic_delivery` requires an accepted decision, canonical task order, and allowed delivery states, but does not require verbatim inclusion of every observation ID. `evidence_complete` reports that traceability requirement separately.",
        "",
        "| Method | Schema-valid executions | Fault decision | Fault order | Fault semantic delivery | Fault evidence | Primary oracle |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report["methods"]:
        denominator = item["fault_denominator"]
        lines.append(
            f"| {item['method']} | {item['execution_schema_valid_rate']:.3f} | {item['fault_decision_accepted_rate']:.3f} ({item['fault_decision_accepted_count']}/{denominator}) | {item['fault_canonical_order_rate']:.3f} ({item['fault_canonical_order_count']}/{denominator}) | {item['fault_semantic_delivery_rate']:.3f} ({item['fault_semantic_delivery_count']}/{denominator}) | {item['fault_evidence_complete_rate']:.3f} ({item['fault_evidence_complete_count']}/{denominator}) | {item['fault_oracle_pass_rate']:.3f} ({item['fault_oracle_pass_count']}/{denominator}) |"
        )
    lines.extend(
        [
            "",
            "## Semantic Delivery Differences",
            "",
            "These comparisons are diagnostic, not the confirmatory primary endpoint. Positive values favor `llm_full_contract_kg`.",
            "",
            "| Comparator | Difference | Scenario-cluster bootstrap 95% | Full-only | Comparator-only | McNemar exact p |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in report["semantic_delivery_paired_comparisons"]:
        interval = item["scenario_cluster_bootstrap_95"] or [0.0, 0.0]
        lines.append(
            f"| {item['comparator']} | {item['difference_vs_full_kg']:.3f} | [{interval[0]:.3f}, {interval[1]:.3f}] | {item['full_kg_only_pass']} | {item['comparator_only_pass']} | {item['mcnemar_exact_p']:.6f} |"
        )
    lines.extend(
        [
            "",
            "## Scenario Decomposition",
            "",
            "Cells show `semantic delivery / primary oracle` case-majority passes.",
            "",
            "| Scenario | llm_only | llm_capability_kg | llm_full_contract_kg | rules_only | fixed_workflow |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for item in report["scenario_results"]:
        cells = []
        for method in experiment.PRIMARY_METHODS:
            value = item[method]
            cells.append(
                f"{value['semantic_delivery_count']}/{value['oracle_pass_count']} of {value['total']}"
            )
        lines.append(f"| {item['scenario']} | {' | '.join(cells)} |")
    return "\n".join(lines) + "\n"


def render_interpretation(report: dict[str, Any], summary: dict[str, Any]) -> str:
    primary = summary["confirmatory_statistics"]
    primary_methods = {item["method"]: item for item in primary["methods"]}
    primary_comparisons = {
        item["comparator"]: item for item in primary["paired_fault_comparisons"]
    }
    diagnostic_methods = {item["method"]: item for item in report["methods"]}
    diagnostic_comparisons = {
        item["comparator"]: item for item in report["semantic_delivery_paired_comparisons"]
    }
    full = primary_methods["llm_full_contract_kg"]
    rules = primary_methods["rules_only"]
    primary_rules = primary_comparisons["rules_only"]
    semantic_full = diagnostic_methods["llm_full_contract_kg"]
    semantic_rules = diagnostic_methods["rules_only"]
    semantic_rules_difference = diagnostic_comparisons["rules_only"]
    semantic_capability_difference = diagnostic_comparisons["llm_capability_kg"]
    return "\n".join(
        [
            "# Held-out Confirmatory Interpretation",
            "",
            "## Primary result",
            "",
            f"The confirmatory composite did not establish superiority: `llm_full_contract_kg` passed {full['fault_majority_pass_count']}/{full['fault_denominator']} fault cases ({full['fault_majority_pass_rate']:.3f}) versus {rules['fault_majority_pass_count']}/{rules['fault_denominator']} ({rules['fault_majority_pass_rate']:.3f}) for `rules_only`. The paired difference was {primary_rules['difference_vs_full_kg']:.3f}, with scenario-cluster bootstrap 95% interval [{primary_rules['scenario_cluster_bootstrap_95'][0]:.3f}, {primary_rules['scenario_cluster_bootstrap_95'][1]:.3f}] and descriptive McNemar p={primary_rules['mcnemar_exact_p']:.3f}.",
            "",
            "The primary endpoint jointly requires a correct decision, canonical tasks and states, grounded source/algorithm use, and verbatim evidence-anchor coverage. Its interval includes zero, so the earlier adversarial result is not independently confirmed under this stricter composite.",
            "",
            "## Secondary diagnostic",
            "",
            f"A semantic-planning advantage remains visible but is post-hoc: full KG achieved {semantic_full['fault_semantic_delivery_count']}/{semantic_full['fault_denominator']} ({semantic_full['fault_semantic_delivery_rate']:.3f}) semantic-delivery passes, versus {semantic_rules['fault_semantic_delivery_count']}/{semantic_rules['fault_denominator']} ({semantic_rules['fault_semantic_delivery_rate']:.3f}) for rules. The difference was {semantic_rules_difference['difference_vs_full_kg']:.3f}, with scenario-cluster interval [{semantic_rules_difference['scenario_cluster_bootstrap_95'][0]:.3f}, {semantic_rules_difference['scenario_cluster_bootstrap_95'][1]:.3f}]. Against capability KG, the diagnostic difference was {semantic_capability_difference['difference_vs_full_kg']:.3f}, interval [{semantic_capability_difference['scenario_cluster_bootstrap_95'][0]:.3f}, {semantic_capability_difference['scenario_cluster_bootstrap_95'][1]:.3f}].",
            "",
            "This diagnostic advantage is concentrated in alias resolution, canonical precedence, poisoned candidate-plan correction, and quality degradation. It cannot be promoted to the primary conclusion without a new predeclared experiment that separates semantic correctness from evidence completeness.",
            "",
            "## Reliability and gaps",
            "",
            f"Full KG schema-valid execution rate was {semantic_full['execution_schema_valid_rate']:.3f}; 13/720 full-KG executions returned schema-invalid plans. All methods scored 0/10 on the primary implicit hard-veto cases. Actual acquisition, algorithm execution, quality writeback, and delivery writeback were not executed.",
            "",
            "Therefore this run supports a bounded hypothesis that full KG improves semantic planning, but it does not confirm end-to-end or composite planning superiority.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()
    rows_path = args.run_dir / "rows.json"
    rows = json.loads(rows_path.read_text(encoding="utf-8"))
    summary = json.loads((args.run_dir / "summary.json").read_text(encoding="utf-8"))
    report = analyze(rows)
    report["evidence"] = {
        "rows_sha256": sha256_file(rows_path),
        "analysis_script_sha256": sha256_file(Path(__file__).resolve()),
    }
    (args.run_dir / "diagnostic_decomposition.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.run_dir / "diagnostic_decomposition.md").write_text(render(report), encoding="utf-8")
    (args.run_dir / "confirmatory_interpretation.md").write_text(
        render_interpretation(report, summary), encoding="utf-8"
    )
    print(json.dumps({"run_dir": str(args.run_dir.resolve()), "status": report["status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
