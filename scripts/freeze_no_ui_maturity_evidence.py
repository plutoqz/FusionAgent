from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OPERATOR_CONTRACT_PATH = (
    REPO_ROOT / "docs/superpowers/specs/2026-04-21-operator-read-model-contract.md"
)


def freeze_no_ui_maturity_evidence(
    target_path: Path,
    gap_ledger_path: Path,
    paper_evidence_path: Path,
    scenario_evidence_path: Path,
    output_json: Path,
    output_markdown: Path,
    operator_contract_path: Path | None = None,
) -> dict[str, Any]:
    target_path = Path(target_path)
    gap_ledger_path = Path(gap_ledger_path)
    paper_evidence_path = Path(paper_evidence_path)
    scenario_evidence_path = Path(scenario_evidence_path)
    operator_contract_path = Path(
        operator_contract_path or DEFAULT_OPERATOR_CONTRACT_PATH
    )
    paper_summary = _load_companion_json(paper_evidence_path)
    scenario_summary = _load_companion_json(scenario_evidence_path)

    source_presence = {
        "maturity_target_present": target_path.exists(),
        "gap_ledger_present": gap_ledger_path.exists(),
        "paper_evidence_present": paper_evidence_path.exists(),
        "scenario_evidence_present": scenario_evidence_path.exists(),
        "operator_contract_present": operator_contract_path.exists(),
    }
    gates = _build_gates(
        source_presence=source_presence,
        paper_summary=paper_summary,
        scenario_summary=scenario_summary,
    )
    payload: dict[str, Any] = {
        **source_presence,
        "gates": gates,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evidence_sources": {
            "maturity_target": _source_record(target_path),
            "gap_ledger": _source_record(gap_ledger_path),
            "paper_evidence": _source_record(paper_evidence_path),
            "scenario_evidence": _source_record(scenario_evidence_path),
            "operator_contract": _source_record(operator_contract_path),
        },
        "paper_blocking_rows": gates["paper_evidence_no_open_blockers"]["blocking_rows"],
        "remaining_boundaries": _remaining_boundaries(
            source_presence=source_presence,
            paper_summary=paper_summary,
            scenario_summary=scenario_summary,
        ),
    }

    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    output_markdown = Path(output_markdown)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text(_render_markdown(payload), encoding="utf-8")
    return payload


def _load_companion_json(markdown_path: Path) -> dict[str, Any] | None:
    companion_json = markdown_path.with_suffix(".json")
    if not companion_json.exists():
        return None
    return json.loads(companion_json.read_text(encoding="utf-8"))


def _source_record(path: Path) -> dict[str, Any]:
    try:
        display_path = path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        display_path = path.as_posix()
    return {
        "path": display_path,
        "present": path.exists(),
    }


def _build_gates(
    *,
    source_presence: dict[str, bool],
    paper_summary: dict[str, Any] | None,
    scenario_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    all_sources_present = all(source_presence.values())
    boundary_rows = _paper_boundary_rows(paper_summary)
    blocking_rows = [
        row
        for row in boundary_rows
        if row["expected_status"] == "passed" and row["observed_status"] != "passed"
    ]
    scenario_count = int((scenario_summary or {}).get("scenario_count") or 0)
    scenario_names = [
        str(item.get("scenario_name") or item.get("scenario_id") or "unnamed")
        for item in (scenario_summary or {}).get("scenarios", [])
        if isinstance(item, dict)
    ]
    paper_gate_passed = paper_summary is not None and not blocking_rows
    scenario_gate_passed = scenario_summary is not None and scenario_count > 0
    return {
        "source_files_present": {
            "passed": all_sources_present,
            "details": dict(source_presence),
        },
        "paper_evidence_no_open_blockers": {
            "passed": paper_gate_passed,
            "blocking_rows": blocking_rows,
        },
        "scenario_evidence_frozen": {
            "passed": scenario_gate_passed,
            "scenario_count": scenario_count,
            "scenario_names": scenario_names,
        },
        "readme_repositioning_ready": {
            "passed": all_sources_present and paper_gate_passed and scenario_gate_passed,
            "reason": "Requires all source freeze files plus no pending/failed paper evidence blockers.",
        },
    }


def _paper_boundary_rows(paper_summary: dict[str, Any] | None) -> list[dict[str, Any]]:
    if paper_summary is None:
        return []
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, str, str]] = set()
    for row in paper_summary.get("rows", []):
        if not isinstance(row, dict):
            continue
        observed_status = _normalized_status(row.get("observed_status"))
        if observed_status == "passed":
            continue
        _append_paper_boundary_row(rows, seen, row, default_expected_status="passed")

    for row in paper_summary.get("failure_rows", []):
        if isinstance(row, dict):
            _append_paper_boundary_row(rows, seen, row, default_expected_status="unknown")
    return rows


def _append_paper_boundary_row(
    rows: list[dict[str, Any]],
    seen: set[tuple[Any, str, str]],
    row: dict[str, Any],
    *,
    default_expected_status: str,
) -> None:
    expected_status = _normalized_status(row.get("expected_status"), default=default_expected_status)
    observed_status = _normalized_status(row.get("observed_status"))
    key = (row.get("row_id"), expected_status, observed_status)
    if key in seen:
        return
    seen.add(key)
    rows.append(
        {
            "row_id": row.get("row_id"),
            "expected_status": expected_status,
            "observed_status": observed_status,
            "analysis": row.get("analysis"),
        }
    )


def _normalized_status(value: Any, *, default: str = "unknown") -> str:
    if value is None:
        return default
    return str(value).strip().lower() or default


def _remaining_boundaries(
    *,
    source_presence: dict[str, bool],
    paper_summary: dict[str, Any] | None,
    scenario_summary: dict[str, Any] | None,
) -> list[str]:
    boundaries: list[str] = []
    missing_sources = [name for name, present in source_presence.items() if not present]
    if missing_sources:
        boundaries.append(f"Missing source files keep the maturity freeze incomplete: {', '.join(missing_sources)}.")

    for blocker in _paper_boundary_rows(paper_summary):
        boundaries.append(
            f"Paper evidence row `{blocker.get('row_id')}` remains {blocker.get('observed_status')} "
            f"against expected {blocker.get('expected_status')}."
        )

    scenario_count = int((scenario_summary or {}).get("scenario_count") or 0)
    if scenario_summary is None:
        boundaries.append("Scenario evidence companion JSON is absent, so scenario freeze completeness is not independently checked.")
    elif scenario_count == 0:
        boundaries.append("Scenario evidence freeze contains no scenarios.")

    boundaries.extend(
        [
            "No-UI maturity excludes final visual frontend, multi-user authentication, production cloud guarantees, and arbitrary task-family extensibility.",
            "Water and bounded POI evidence retain partial execution semantics and must not be described as zero-cost new-topic expansion.",
            "Trajectory-to-road remains reservation-only because live runtime trajectory ingestion is not proven.",
            "Durable learning is frozen as bounded policy-hint evidence, not full policy auto-tuning.",
            "Operator-facing maturity is limited to read APIs, CLI scripts, runbooks, and evidence artifacts rather than a frontend.",
        ]
    )
    return boundaries


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# No-UI Maturity Evidence Freeze",
        "",
        f"- Generated at: `{payload['generated_at']}`",
        f"- README repositioning ready: {_status(payload['gates']['readme_repositioning_ready']['passed'])}",
        "",
        "## Gate Status",
        "",
    ]
    for gate_name, gate in payload["gates"].items():
        lines.append(f"- `{gate_name}`: {_status(bool(gate.get('passed')))}")
        for key, value in gate.items():
            if key == "passed":
                continue
            lines.append(f"  - {key}: `{json.dumps(value, ensure_ascii=False, sort_keys=True)}`")
    lines.extend(["", "## Evidence Sources", ""])
    for source_name, source in payload["evidence_sources"].items():
        field_name = f"{source_name}_present"
        if source_name == "maturity_target":
            field_name = "maturity_target_present"
        elif source_name == "gap_ledger":
            field_name = "gap_ledger_present"
        lines.append(
            f"- `{field_name}`: {_status(bool(source['present']))}; path: `{source['path']}`"
        )
    lines.extend(["", "## Remaining Boundaries", ""])
    for boundary in payload["remaining_boundaries"]:
        lines.append(f"- {boundary}")
    lines.append("")
    return "\n".join(lines)


def _status(passed: bool) -> str:
    return "pass" if passed else "not passed"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze no-UI maturity evidence and gate status.")
    parser.add_argument("--target", required=True, help="No-UI maturity target Markdown path.")
    parser.add_argument("--gap-ledger", required=True, help="No-UI maturity gap ledger Markdown path.")
    parser.add_argument("--paper-evidence", required=True, help="Paper evidence freeze Markdown path.")
    parser.add_argument("--scenario-evidence", required=True, help="Scenario evidence freeze Markdown path.")
    parser.add_argument(
        "--operator-contract",
        default=str(DEFAULT_OPERATOR_CONTRACT_PATH),
        help="Operator read-model contract Markdown path.",
    )
    parser.add_argument("--output-json", required=True, help="Output JSON path.")
    parser.add_argument("--output-markdown", required=True, help="Output Markdown path.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    freeze_no_ui_maturity_evidence(
        target_path=Path(args.target),
        gap_ledger_path=Path(args.gap_ledger),
        paper_evidence_path=Path(args.paper_evidence),
        scenario_evidence_path=Path(args.scenario_evidence),
        output_json=Path(args.output_json),
        output_markdown=Path(args.output_markdown),
        operator_contract_path=Path(args.operator_contract),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
