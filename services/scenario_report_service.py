from __future__ import annotations

from pathlib import Path
from typing import Any


TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates" / "reports"


def render_scenario_reports(*, summary: dict[str, Any], documents_dir: Path) -> dict[str, str]:
    documents_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "zh": str(documents_dir / "scenario_report.zh.md"),
        "en": str(documents_dir / "scenario_report.en.md"),
    }
    Path(outputs["zh"]).write_text(_render_zh(summary), encoding="utf-8")
    Path(outputs["en"]).write_text(_render_en(summary), encoding="utf-8")
    return outputs


def _render_zh(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {summary.get('scenario_name', 'scenario run')} 场景报告",
            "",
            "## 场景概述",
            f"- 场景 ID：{summary.get('scenario_id', 'unknown')}",
            f"- 灾害类型：{summary.get('disaster_type') or 'unknown'}",
            f"- 子任务数量：{len(summary.get('child_runs', []))}",
            "",
            "## 知识图谱关系链",
            *_trace_lines(summary.get("kg_path_traces", [])),
            "",
            "## 最终执行工作流",
            *_workflow_lines(summary.get("workflow_traces", [])),
            "",
            "## 数据源覆盖与退化",
            *_generic_lines(summary.get("source_coverage", []), empty="未记录数据源覆盖信息。"),
            "",
            "## 数据融合结果评价指标",
            *_generic_lines(summary.get("evaluation", {}).get("data_fusion_metrics", []), empty="未生成可读取的数据融合指标。"),
            "",
            "## 智能体评价指标",
            str(summary.get("evaluation", {}).get("agentic_metrics", {})),
            "",
            "## 自进化证据",
            str(summary.get("evaluation", {}).get("self_evolution", {})),
            "",
            "## 输出文件",
            *_generic_lines(summary.get("final_outputs", []), empty="未记录输出文件。"),
            "",
        ]
    )


def _render_en(summary: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# {summary.get('scenario_name', 'scenario run')} Scenario Report",
            "",
            "## Scenario Overview",
            f"- Scenario ID: {summary.get('scenario_id', 'unknown')}",
            f"- Disaster type: {summary.get('disaster_type') or 'unknown'}",
            f"- Child runs: {len(summary.get('child_runs', []))}",
            "",
            "## KG Relationship Chain",
            *_trace_lines(summary.get("kg_path_traces", [])),
            "",
            "## Final Execution Workflow",
            *_workflow_lines(summary.get("workflow_traces", [])),
            "",
            "## Source Coverage And Fallbacks",
            *_generic_lines(summary.get("source_coverage", []), empty="No source coverage evidence was recorded."),
            "",
            "## Data Fusion Evaluation Metrics",
            *_generic_lines(summary.get("evaluation", {}).get("data_fusion_metrics", []), empty="No readable data-fusion metrics were generated."),
            "",
            "## Agentic Evaluation Metrics",
            str(summary.get("evaluation", {}).get("agentic_metrics", {})),
            "",
            "## Self-Evolution Evidence",
            str(summary.get("evaluation", {}).get("self_evolution", {})),
            "",
            "## Output Files",
            *_generic_lines(summary.get("final_outputs", []), empty="No output files were recorded."),
            "",
        ]
    )


def _trace_lines(traces: list[Any]) -> list[str]:
    if not traces:
        return ["- none"]
    return [f"- {trace.get('workflow_id', 'unknown')}: {trace.get('selected_pattern_id', 'unknown')}" for trace in traces if isinstance(trace, dict)]


def _workflow_lines(traces: list[Any]) -> list[str]:
    lines: list[str] = []
    for trace in traces:
        if not isinstance(trace, dict):
            continue
        for step in trace.get("steps", []):
            if isinstance(step, dict):
                lines.append(f"- {step.get('step_name')}: {step.get('status')}")
    return lines or ["- none"]


def _generic_lines(items: list[Any], *, empty: str) -> list[str]:
    if not items:
        return [f"- {empty}"]
    return [f"- {item}" for item in items]
