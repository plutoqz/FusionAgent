from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


EXPECTED_CASES = {f"C{index:02d}" for index in range(1, 7)}
EXPECTED_GROUPS = {"fixed_workflow", "rules_only", "kg_only"}
EXPECTED_REPLICATES = {1, 2, 3}
PROTOCOL_ID = "fusionagent.planning-repeated-formal.v2"


def audit_deterministic_repeated(result_path: Path) -> dict[str, Any]:
    report = _read_json(result_path)
    rows = report.get("runs", [])
    cells: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        cells[(row.get("case_id"), row.get("group"))].append(row)
    expected_cells = {(case_id, group) for case_id in EXPECTED_CASES for group in EXPECTED_GROUPS}
    actual_grid = {
        (row.get("case_id"), row.get("group"), row.get("replicate")) for row in rows
    }
    expected_grid = {
        (case_id, group, replicate)
        for case_id in EXPECTED_CASES
        for group in EXPECTED_GROUPS
        for replicate in EXPECTED_REPLICATES
    }
    checks = {
        "report_type": report.get("report_type") == "planning_only_deterministic_repeated_formal",
        "protocol_id": report.get("protocol_id") == PROTOCOL_ID,
        "run_count": report.get("run_count") == len(rows) == 54,
        "repetitions": report.get("repetitions") == 3,
        "exact_case_group_replicate_grid": actual_grid == expected_grid,
        "all_cells_present": set(cells) == expected_cells,
        "input_hash_stable_within_cell": all(
            len({row.get("input_hash") for row in items}) == 1 for items in cells.values()
        ),
        "output_hash_stable_within_cell": all(
            len({row.get("output_hash") for row in items}) == 1 for items in cells.values()
        ),
        "pre_fallback_valid_all_rows": all(
            row.get("evaluation", {}).get("pre_fallback_valid") is True for row in rows
        ),
        "negative_control_declared": set(report.get("negative_control_case_ids", [])) == {"C03"},
        "execution_commit_recorded": isinstance(report.get("execution_commit"), str)
        and len(report["execution_commit"]) == 40,
    }
    blockers = [name for name, passed in checks.items() if not passed]
    return {
        "report_type": "planning_only_deterministic_repeated_independent_audit",
        "protocol_id": PROTOCOL_ID,
        "source_result": {
            "path": str(result_path.resolve()),
            "sha256": _file_hash(result_path),
            "size_bytes": result_path.stat().st_size,
        },
        "checks": checks,
        "passed": not blockers,
        "blockers": blockers,
        "run_count": len(rows),
        "cell_count": len(cells),
        "group_metrics": [_group_metric(group, rows) for group in sorted(EXPECTED_GROUPS)],
        "claim_boundary": (
            "Exact deterministic repetition verifies implementation stability only. "
            "Repeated rows are not independent stochastic samples and do not support significance claims."
        ),
    }


def _group_metric(group: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    items = [row for row in rows if row.get("group") == group]
    positive = [row for row in items if row.get("case_id") != "C03"]
    return {
        "group": group,
        "runs": len(items),
        "mean_automatic_score_all_rows": _mean_score(items),
        "mean_automatic_score_positive_rows": _mean_score(positive),
        "runs_all_automatic_checks_passed": sum(
            all(check.get("passed") is True for check in row["evaluation"]["automatic_checks"])
            for row in items
        ),
    }


def _mean_score(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    return round(sum(row["evaluation"]["automatic_score"] for row in rows) / len(rows), 6)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _file_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit repeated deterministic planning evidence.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError(f"Refusing to overwrite deterministic audit: {args.output}")
    audit = audit_deterministic_repeated(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0 if audit["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
