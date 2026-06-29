from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


REQUIRED_AUDIT_EVENTS: tuple[str, ...] = (
    "run_created",
    "plan_created",
    "plan_validated",
    "task_inputs_resolved",
    "execution_completed",
    "output_schema_validated",
    "run_succeeded",
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validation_payload(inspection: dict[str, Any]) -> dict[str, Any]:
    direct = inspection.get("validation")
    if isinstance(direct, dict):
        return direct
    plan = inspection.get("plan")
    if isinstance(plan, dict) and isinstance(plan.get("validation"), dict):
        return dict(plan["validation"])
    return {}


def _artifact_payload(inspection: dict[str, Any]) -> dict[str, Any]:
    artifact = inspection.get("artifact")
    if isinstance(artifact, dict):
        return artifact
    run = inspection.get("run")
    if isinstance(run, dict) and isinstance(run.get("artifact"), dict):
        return dict(run["artifact"])
    return {}


def _resolve_artifact_path(path_value: Any) -> Path | None:
    if not path_value:
        return None
    path = Path(str(path_value))
    return path if path.is_absolute() else REPO_ROOT / path


def _audit_events(inspection: dict[str, Any]) -> list[dict[str, Any]]:
    events = inspection.get("audit_events")
    if not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, dict)]


def _event_kinds(inspection: dict[str, Any]) -> list[str]:
    return [str(event.get("kind") or "") for event in _audit_events(inspection) if event.get("kind")]


def _plan_created_details(inspection: dict[str, Any]) -> dict[str, Any]:
    for event in _audit_events(inspection):
        if event.get("kind") != "plan_created":
            continue
        details = event.get("details")
        return details if isinstance(details, dict) else {}
    return {}


def _validation_issue_codes(validation: dict[str, Any]) -> list[str]:
    issues = validation.get("issues")
    if not isinstance(issues, list):
        return []
    return [
        str(issue.get("code") or "")
        for issue in issues
        if isinstance(issue, dict) and issue.get("code")
    ]


def _kg_grounding_score(inspection: dict[str, Any], plan_details: dict[str, Any]) -> float:
    trace = inspection.get("kg_path_trace")
    if isinstance(trace, dict):
        report = trace.get("grounding_report")
        if isinstance(report, dict) and isinstance(report.get("grounding_score"), int | float):
            return float(report["grounding_score"])
    value = plan_details.get("grounding_score")
    return float(value) if isinstance(value, int | float) else 0.0


def summarize_inspection_trace(path: Path) -> dict[str, Any]:
    inspection = _load_json(path)
    run = inspection.get("run") if isinstance(inspection.get("run"), dict) else {}
    validation = _validation_payload(inspection)
    plan_details = _plan_created_details(inspection)
    event_kinds = _event_kinds(inspection)
    event_presence = {kind: kind in event_kinds for kind in REQUIRED_AUDIT_EVENTS}
    artifact = _artifact_payload(inspection)
    artifact_path = _resolve_artifact_path(artifact.get("path"))
    kg_trace = inspection.get("kg_path_trace") if isinstance(inspection.get("kg_path_trace"), dict) else {}
    kg_chains = kg_trace.get("chains") if isinstance(kg_trace.get("chains"), list) else []
    decision_records = run.get("decision_records") if isinstance(run.get("decision_records"), list) else []
    artifact_size = int(artifact.get("size_bytes") or 0)
    artifact_declared = bool(artifact.get("path")) and artifact_size > 0

    return {
        "case_id": Path(path).stem,
        "source_inspection": str(Path(path)).replace("\\", "/"),
        "inspection_sha256": _sha256_file(path),
        "run_id": run.get("run_id"),
        "job_type": run.get("job_type"),
        "phase": run.get("phase"),
        "validation_valid": bool(validation.get("valid", False)),
        "validation_issue_codes": _validation_issue_codes(validation),
        "grounding_score": _kg_grounding_score(inspection, plan_details),
        "audit_event_count": len(event_kinds),
        "required_audit_events_present": event_presence,
        "decision_record_count": len(decision_records),
        "selected_decisions": plan_details.get("selected_decisions") if isinstance(plan_details.get("selected_decisions"), dict) else {},
        "kg_trace_chain_count": len(kg_chains),
        "selected_pattern_id": kg_trace.get("selected_pattern_id"),
        "artifact_declared": artifact_declared,
        "artifact_path": str(artifact.get("path") or "").replace("\\", "/"),
        "artifact_size_bytes": artifact_size,
        "artifact_path_exists_in_workspace": bool(artifact_path and artifact_path.exists()),
        "inspection_trace_complete": all(event_presence.values()) and bool(kg_chains) and artifact_declared,
    }


def export_trace_evidence(
    paths: list[Path],
    *,
    output_json: Path,
    output_markdown: Path | None = None,
) -> dict[str, Any]:
    rows = [summarize_inspection_trace(path) for path in paths]
    payload = {
        "source": "trace-backed-a2c-ablation-evidence",
        "scope": (
            "Inspection-backed A2c provenance table. It verifies audit-event and KG-trace "
            "presence in frozen inspection payloads; it does not rerun live LLM/API/KG calls."
        ),
        "required_audit_events": list(REQUIRED_AUDIT_EVENTS),
        "case_count": len(rows),
        "inspection_trace_complete_case_count": sum(
            1 for row in rows if row["inspection_trace_complete"]
        ),
        "artifact_declared_case_count": sum(1 for row in rows if row["artifact_declared"]),
        "artifact_file_present_case_count": sum(
            1 for row in rows if row["artifact_path_exists_in_workspace"]
        ),
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
        "# Trace-Backed A2c Ablation Evidence",
        "",
        payload["scope"],
        "",
        f"- Cases: {payload['case_count']}",
        f"- Inspection trace complete cases: {payload['inspection_trace_complete_case_count']}",
        f"- Artifact declared cases: {payload['artifact_declared_case_count']}",
        f"- Artifact files present in current workspace: {payload['artifact_file_present_case_count']}",
        "",
        "| Case | Job | Phase | Valid | Grounding | Events | KG Chains | Artifact Declared | Artifact File Present | Trace Complete |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for row in payload["rows"]:
        lines.append(
            "| {case_id} | {job_type} | {phase} | {validation_valid} | {grounding_score} | "
            "{audit_event_count} | {kg_trace_chain_count} | {artifact_declared} | "
            "{artifact_path_exists_in_workspace} | {inspection_trace_complete} |".format(**row)
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export trace-backed evidence for A2c inspection rows.")
    parser.add_argument("--input", action="append", required=True, help="Inspection JSON path.")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", default="")
    args = parser.parse_args(argv)
    payload = export_trace_evidence(
        [Path(item) for item in args.input],
        output_json=Path(args.output_json),
        output_markdown=Path(args.output_markdown) if args.output_markdown else None,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
