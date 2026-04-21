from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def freeze_scenario_evidence(
    scenario_dirs: List[Path],
    output_json: Path,
    output_markdown: Path,
) -> Dict[str, Any]:
    scenarios = [_freeze_scenario_dir(Path(scenario_dir)) for scenario_dir in scenario_dirs]
    payload = {
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
    }
    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    output_markdown = Path(output_markdown)
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text(_render_markdown(payload), encoding="utf-8")
    return payload


def _freeze_scenario_dir(scenario_dir: Path) -> Dict[str, Any]:
    summary = _load_json(scenario_dir / "scenario_summary.json")
    evaluation = dict(summary.get("evaluation") or {})
    kg_path_traces = _list_from_summary_or_file(summary, "kg_path_traces", scenario_dir / "kg_path_trace.json")
    workflow_traces = _list_from_summary_or_file(summary, "workflow_traces", scenario_dir / "workflow_trace.json")
    return {
        "scenario_id": summary.get("scenario_id"),
        "scenario_name": summary.get("scenario_name"),
        "agentic_metrics": dict(evaluation.get("agentic_metrics") or {}),
        "self_evolution": dict(evaluation.get("self_evolution") or {}),
        "kg_path_trace_count": len(kg_path_traces),
        "workflow_trace_count": len(workflow_traces),
        "document_paths": dict(summary.get("document_paths") or {}),
        "source_dir": str(scenario_dir),
    }


def _load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _list_from_summary_or_file(summary: Dict[str, Any], key: str, path: Path) -> List[Any]:
    value = summary.get(key)
    if isinstance(value, list):
        return value
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, list) else []


def _render_markdown(payload: Dict[str, Any]) -> str:
    lines = [
        "# Scenario Evidence Freeze",
        "",
        f"- Scenario count: {payload['scenario_count']}",
        "",
    ]
    for scenario in payload["scenarios"]:
        lines.extend(
            [
                f"## {scenario.get('scenario_name') or 'Unnamed scenario'}",
                "",
                f"- Scenario ID: `{scenario.get('scenario_id')}`",
                f"- Source directory: `{scenario.get('source_dir')}`",
                f"- KG path trace count: {scenario.get('kg_path_trace_count')}",
                f"- Workflow trace count: {scenario.get('workflow_trace_count')}",
                f"- Agentic metrics: `{json.dumps(scenario.get('agentic_metrics') or {}, ensure_ascii=False, sort_keys=True)}`",
                f"- Self-evolution: `{json.dumps(scenario.get('self_evolution') or {}, ensure_ascii=False, sort_keys=True)}`",
                f"- Document paths: `{json.dumps(scenario.get('document_paths') or {}, ensure_ascii=False, sort_keys=True)}`",
                "",
            ]
        )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Freeze scenario evidence for paper/demo reporting.")
    parser.add_argument("--scenario-dir", action="append", required=True, help="Scenario output directory.")
    parser.add_argument("--output-json", required=True, help="Output JSON path.")
    parser.add_argument("--output-markdown", required=True, help="Output Markdown path.")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    freeze_scenario_evidence(
        [Path(item) for item in args.scenario_dir],
        Path(args.output_json),
        Path(args.output_markdown),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
