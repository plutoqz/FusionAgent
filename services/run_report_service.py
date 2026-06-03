from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from schemas.agent import RunEvent, RunStatus, WorkflowPlan
from services.artifact_evaluation_service import evaluate_agentic_run, evaluate_vector_artifact
from services.kg_path_trace_service import build_kg_path_trace
from services.report_quality_service import build_report_quality_summary
from services.run_recovery_service import build_recovery_hint
from services.run_telemetry_service import build_run_telemetry_summary
from services.workflow_trace_service import build_workflow_trace


def build_run_report_summary(
    *,
    status: RunStatus,
    plan: WorkflowPlan | None,
    audit_events: list[RunEvent],
    artifact_path: Path | None,
    telemetry_summary: dict[str, Any] | None = None,
    source_semantic_contract: dict[str, Any] | None = None,
    recovery_worker_evidence: dict[str, Any] | None = None,
    digest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    agentic_metrics = (
        evaluate_agentic_run(
            plan=plan,
            decision_records=status.decision_records,
            audit_events=audit_events,
            durable_learning_summary=_durable_learning_summary(plan),
            manual_intervention_count=0,
        )
        if plan is not None
        else {"manual_intervention_count": 0}
    )
    artifact_metrics = _artifact_metrics(artifact_path)
    recovery_hint = build_recovery_hint(status.model_dump(mode="json"))
    quality_summary = build_report_quality_summary(
        job_type=status.job_type.value,
        audit_events=audit_events,
        source_semantic_contract=source_semantic_contract or {},
        artifact_metrics=artifact_metrics,
        recovery_evidence=recovery_hint,
    )
    source_coverage = _source_coverage_from_events(audit_events)
    degradation = _degradation_summary_from_source_coverage(source_coverage)
    return {
        "run_id": status.run_id,
        "job_type": status.job_type.value,
        "phase": status.phase.value,
        "trigger": status.trigger.model_dump(mode="json"),
        "target_crs": status.target_crs,
        "created_at": status.created_at,
        "started_at": status.started_at,
        "finished_at": status.finished_at,
        "artifact": _artifact_summary(status=status, artifact_path=artifact_path),
        "kg_path_trace": build_kg_path_trace(plan) if plan is not None else {},
        "workflow_trace": build_workflow_trace(audit_events),
        "source_coverage": source_coverage,
        "fallback_summary": _fallback_summary_from_events(audit_events),
        "large_area_runtime": _large_area_runtime_from_events(audit_events),
        "degradation": degradation,
        "evaluation": {
            "process": {
                "agentic_metrics": agentic_metrics,
                "telemetry": telemetry_summary
                or build_run_telemetry_summary(status=status, audit_events=audit_events, plan=plan),
                "recovery": {
                    "hint": recovery_hint,
                    "worker_evidence": recovery_worker_evidence or {},
                    "digest": digest or {},
                },
            },
            "result": {
                "artifact_metrics": artifact_metrics,
                "schema_validation": _latest_event_details(audit_events, "output_schema_validated"),
            },
            "self_evolution": {
                "record_written": bool(agentic_metrics.get("self_evolution_record_written")),
                "hint_available": bool(agentic_metrics.get("self_evolution_hint_available")),
                "hint_used": bool(agentic_metrics.get("self_evolution_hint_used")),
                "policy_adjustment": agentic_metrics.get("self_evolution_policy_adjustment", 0.0),
                "learning_opportunity_recorded": bool(
                    agentic_metrics.get("self_evolution_learning_opportunity_recorded")
                ),
                "boundary": "bounded policy hints only; no automatic model, policy, or source catalog mutation",
            },
        },
        "source_semantic_contract": source_semantic_contract or {},
        "quality_summary": quality_summary,
        "evidence_readiness": {
            "score": quality_summary["evidence_readiness_score"],
            "boundary": quality_summary["quality_boundary"],
        },
    }


def render_run_reports(*, summary: dict[str, Any], documents_dir: Path) -> dict[str, str]:
    documents_dir.mkdir(parents=True, exist_ok=True)
    summary_path = documents_dir / "run_report_summary.json"
    zh_path = documents_dir / "run_report.zh.md"
    en_path = documents_dir / "run_report.en.md"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    zh_path.write_text(_render_zh(summary), encoding="utf-8")
    en_path.write_text(_render_en(summary), encoding="utf-8")
    return {"summary": str(summary_path), "zh": str(zh_path), "en": str(en_path)}


def _render_zh(summary: dict[str, Any]) -> str:
    evaluation = summary.get("evaluation", {})
    process = evaluation.get("process", {})
    result = evaluation.get("result", {})
    return "\n".join(
        [
            f"# {summary.get('run_id', 'run')} 运行报告",
            "",
            "## 运行概述",
            f"- 任务类型：{summary.get('job_type', 'unknown')}",
            f"- 阶段：{summary.get('phase', 'unknown')}",
            f"- 目标 CRS：{summary.get('target_crs', 'unknown')}",
            "",
            "## 过程评价",
            f"- 智能体指标：{_compact(process.get('agentic_metrics', {}))}",
            f"- 遥测：{_compact(process.get('telemetry', {}))}",
            f"- 恢复结果：{_compact(process.get('recovery', {}))}",
            "",
            "## 结果评价",
            f"- 大范围运行时：{_compact(summary.get('large_area_runtime', {}))}",
            f"- 产物：{_compact(summary.get('artifact', {}))}",
            f"- 产物指标：{_compact(result.get('artifact_metrics', {}))}",
            f"- Schema 校验：{_compact(result.get('schema_validation', {}))}",
            "",
            "## 质量与证据边界",
            f"- {_compact(summary.get('quality_summary', {}))}",
            "",
            "## 数据源覆盖与退化",
            *_generic_lines(summary.get("source_coverage", []), empty="未记录数据源覆盖信息。"),
            *_generic_lines(summary.get("fallback_summary", []), empty="未记录退化或 fallback 事件。"),
            "",
            "## 自进化证据",
            f"- {_compact(evaluation.get('self_evolution', {}))}",
            "",
            "## 知识图谱关系链",
            f"- {_compact(summary.get('kg_path_trace', {}))}",
            "",
        ]
    )


def _render_en(summary: dict[str, Any]) -> str:
    evaluation = summary.get("evaluation", {})
    process = evaluation.get("process", {})
    result = evaluation.get("result", {})
    return "\n".join(
        [
            f"# {summary.get('run_id', 'run')} Run Report",
            "",
            "## Run Overview",
            f"- Job type: {summary.get('job_type', 'unknown')}",
            f"- Phase: {summary.get('phase', 'unknown')}",
            f"- Target CRS: {summary.get('target_crs', 'unknown')}",
            "",
            "## Process Evaluation",
            f"- Agentic metrics: {_compact(process.get('agentic_metrics', {}))}",
            f"- Telemetry: {_compact(process.get('telemetry', {}))}",
            f"- Recovery outcome: {_compact(process.get('recovery', {}))}",
            "",
            "## Result Evaluation",
            f"- Large-area runtime: {_compact(summary.get('large_area_runtime', {}))}",
            f"- Artifact: {_compact(summary.get('artifact', {}))}",
            f"- Artifact metrics: {_compact(result.get('artifact_metrics', {}))}",
            f"- Schema validation: {_compact(result.get('schema_validation', {}))}",
            "",
            "## Quality And Evidence Boundary",
            f"- {_compact(summary.get('quality_summary', {}))}",
            "",
            "## Source Coverage And Fallbacks",
            *_generic_lines(summary.get("source_coverage", []), empty="No source coverage evidence was recorded."),
            *_generic_lines(summary.get("fallback_summary", []), empty="No fallback events were recorded."),
            "",
            "## Self-Evolution Evidence",
            f"- {_compact(evaluation.get('self_evolution', {}))}",
            "",
            "## KG Relationship Chain",
            f"- {_compact(summary.get('kg_path_trace', {}))}",
            "",
        ]
    )


def _artifact_summary(*, status: RunStatus, artifact_path: Path | None) -> dict[str, Any]:
    return {
        "filename": status.artifact.filename if status.artifact is not None else None,
        "path": str(artifact_path) if artifact_path is not None else None,
        "size_bytes": artifact_path.stat().st_size if artifact_path is not None and artifact_path.exists() else None,
        "available": bool(artifact_path is not None and artifact_path.exists()),
    }


def _artifact_metrics(artifact_path: Path | None) -> dict[str, Any]:
    if artifact_path is None:
        return {"artifact_validity": False, "artifact_path": None}
    path = Path(artifact_path)
    if path.suffix.lower() == ".shp":
        try:
            return evaluate_vector_artifact(path, required_fields=["geometry"])
        except Exception as exc:  # noqa: BLE001
            return {"artifact_validity": False, "artifact_path": str(path), "error": f"{type(exc).__name__}: {exc}"}
    return {
        "artifact_validity": path.exists(),
        "artifact_path": str(path),
        "size_bytes": path.stat().st_size if path.exists() else None,
    }


def _source_coverage_from_events(audit_events: list[RunEvent]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for event in audit_events:
        if event.kind != "task_inputs_resolved":
            continue
        component_coverage = event.details.get("component_coverage", {})
        coverage_state, degraded_component_source_ids = _component_coverage_state(component_coverage)
        items.append(
            {
                "requested_source_id": event.details.get("requested_source_id") or event.details.get("source_id"),
                "selected_source_id": event.details.get("selected_source_id") or event.details.get("source_id"),
                "fallback_from_source_id": event.details.get("fallback_from_source_id"),
                "source_mode": event.details.get("source_mode"),
                "cache_hit": event.details.get("cache_hit"),
                "component_coverage": component_coverage,
                "coverage_state": coverage_state,
                "degraded_component_source_ids": degraded_component_source_ids,
            }
        )
    return items


def _component_coverage_state(component_coverage: Any) -> tuple[str, list[str]]:
    if not isinstance(component_coverage, dict) or not component_coverage:
        return "unknown", []
    degraded: list[str] = []
    for source_id, payload in component_coverage.items():
        feature_count = None
        coverage_status = ""
        if isinstance(payload, dict):
            coverage_status = str(payload.get("coverage_status") or "").strip().lower()
            raw_count = payload.get("feature_count")
            try:
                feature_count = int(raw_count) if raw_count is not None else None
            except (TypeError, ValueError):
                feature_count = None
        if coverage_status in {"empty", "missing", "missing_optional_ref", "coverage_empty"} or feature_count == 0:
            degraded.append(str(source_id))
    return ("degraded" if degraded else "available", sorted(degraded))


def _degradation_summary_from_source_coverage(source_coverage: list[dict[str, Any]]) -> dict[str, Any]:
    degraded_components = sorted(
        {
            source_id
            for item in source_coverage
            for source_id in item.get("degraded_component_source_ids", [])
        }
    )
    if not degraded_components:
        return {
            "state": "none",
            "reason_code": None,
            "degraded_component_source_ids": [],
        }
    return {
        "state": "degraded",
        "reason_code": "PARTIAL_SOURCE_COVERAGE",
        "degraded_component_source_ids": degraded_components,
    }


def _fallback_summary_from_events(audit_events: list[RunEvent]) -> list[dict[str, Any]]:
    return [
        {
            "kind": event.kind,
            "source_id": event.details.get("source_id"),
            "selected_source_id": event.details.get("selected_source_id"),
            "reason": event.details.get("reason") or event.message,
        }
        for event in audit_events
        if event.kind in {"source_fallback_selected", "source_coverage_checked"}
    ]


def _large_area_runtime_from_events(audit_events: list[RunEvent]) -> dict[str, Any]:
    for event in reversed(audit_events):
        if event.kind == "large_area_runtime_completed":
            details = dict(event.details or {})
            return {
                "tile_count": details.get("tile_count"),
                "stitched_feature_count": details.get("stitched_feature_count"),
                "evidence_paths": details.get("evidence_paths", {}),
            }
    return {}


def _latest_event_details(audit_events: list[RunEvent], kind: str) -> dict[str, Any]:
    for event in reversed(audit_events):
        if event.kind == kind:
            return dict(event.details or {})
    return {}


def _durable_learning_summary(plan: WorkflowPlan | None) -> dict[str, Any]:
    if plan is None or not isinstance(plan.context, dict):
        return {}
    retrieval = plan.context.get("retrieval", {})
    if not isinstance(retrieval, dict):
        return {}
    durable = retrieval.get("durable_learning_summaries", {})
    return durable if isinstance(durable, dict) else {}


def _compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _generic_lines(items: list[Any], *, empty: str) -> list[str]:
    if not items:
        return [f"- {empty}"]
    return [f"- {_compact(item)}" for item in items]
