from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _coerce_repo_relative(value: str | None, *, repo_root: Path) -> str | None:
    if not value:
        return None

    raw = Path(value)
    if raw.is_absolute():
        try:
            return raw.resolve().relative_to(repo_root.resolve()).as_posix()
        except Exception:
            parts = raw.parts
            for index in range(len(parts)):
                candidate = repo_root / Path(*parts[index:])
                if candidate.exists():
                    return candidate.relative_to(repo_root).as_posix()

    candidate = repo_root / value
    if candidate.exists():
        return candidate.relative_to(repo_root).as_posix()
    return value.replace("\\", "/")


def _normalize_harness_summary(payload: dict[str, Any]) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    for item in payload.get("cases", []):
        if not isinstance(item, dict):
            continue
        evidence = dict(item.get("evidence") or {})
        if "planning_validity" not in evidence:
            evidence["planning_validity"] = item.get("status") == "passed"
        if "artifact_validity" not in evidence:
            evidence["artifact_validity"] = bool(item.get("artifact_size")) and item.get("status") == "passed"
        if "inspection_artifact_available" not in evidence:
            evidence["inspection_artifact_available"] = bool(item.get("artifact_size"))
        if "inspection_download_path" not in evidence:
            run_id = item.get("run_id")
            if run_id and evidence["inspection_artifact_available"]:
                evidence["inspection_download_path"] = f"/api/v2/runs/{run_id}/artifact"
            else:
                evidence["inspection_download_path"] = None
        cases.append({**item, "evidence": evidence})

    return {
        "source_format": "harness-summary",
        "manifest": payload.get("manifest"),
        "base_url": payload.get("base_url"),
        "timeout_sec": payload.get("timeout_sec"),
        "commit_sha": payload.get("commit_sha"),
        "environment": dict(payload.get("environment") or {}),
        "cases": cases,
    }


def _normalize_single_case_result(payload: dict[str, Any]) -> dict[str, Any]:
    artifact_size = payload.get("artifact_size_bytes", payload.get("artifact_size"))
    return {
        "source_format": "single-case-result",
        "manifest": (payload.get("evidence_origin") or {}).get("manifest"),
        "base_url": (payload.get("runner") or {}).get("base_url"),
        "timeout_sec": (payload.get("runner") or {}).get("timeout_seconds"),
        "commit_sha": payload.get("commit_sha"),
        "environment": dict(payload.get("environment") or {}),
        "cases": [
            {
                "case_id": str(payload.get("case_id") or ""),
                "case_name": payload.get("case_name"),
                "status": payload.get("status"),
                "run_id": payload.get("run_id"),
                "duration_ms": payload.get("duration_ms"),
                "timeout_sec": (payload.get("runner") or {}).get("timeout_seconds"),
                "artifact_size": artifact_size,
                "inputs": dict(payload.get("inputs") or {}),
                "notes": list(payload.get("notes") or []),
                "evidence": {
                    "planning_validity": payload.get("status") == "passed",
                    "artifact_validity": bool(artifact_size),
                    "inspection_artifact_available": bool(artifact_size),
                    "inspection_download_path": None,
                },
            }
        ],
    }


def _normalize_summary_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("cases"), list):
        return _normalize_harness_summary(payload)
    if payload.get("case_id"):
        return _normalize_single_case_result(payload)
    raise ValueError("Unsupported evidence summary format.")


def _metric_value(name: str, *, case: dict[str, Any], row: dict[str, Any]) -> str:
    evidence = case.get("evidence") or {}
    if row.get("summary_kind") == "verification":
        if name in {
            "execution_success_rate",
            "planning_validity_rate",
            "recovery_success_rate",
            "decision_trace_completeness",
        }:
            return "pass" if row.get("observed_status") == "passed" else "fail"
    if name == "execution_success_rate":
        return "pass" if case.get("status") == "passed" else "fail"
    if name == "planning_validity_rate":
        return "pass" if evidence.get("planning_validity") else "fail"
    if name == "artifact_validity":
        return "pass" if evidence.get("artifact_validity") else "fail"
    if name == "evidence_completeness_rate":
        return "pass" if case.get("run_id") and row.get("artifact_storage") else "fail"
    if name == "reproducibility_status":
        return str(row.get("reproducibility") or "unknown")
    return "n/a"


def _freeze_verification_row(row: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    observed_status = str(row.get("observed_status") or "unknown")
    return {
        "row_id": row["row_id"],
        "claim_ids": list(row.get("claim_ids") or []),
        "baseline": row["baseline"],
        "dataset": row["dataset"],
        "case_id": row.get("case_id"),
        "case_name": row.get("case_name"),
        "expected_status": row.get("expected_status") or "passed",
        "observed_status": observed_status,
        "summary_json": None,
        "summary_source_format": "verification",
        "manifest": None,
        "command": row.get("command"),
        "verification_command": list(row.get("verification_command") or []),
        "verification_result": row.get("verification_result"),
        "summary": row.get("summary"),
        "commit_sha": row.get("commit_sha"),
        "base_url": row.get("base_url"),
        "timeout_sec": row.get("timeout_sec"),
        "environment": dict(row.get("environment") or {}),
        "run_id": row.get("run_id"),
        "artifact_storage": row.get("artifact_storage"),
        "raw_artifacts": {
            "run_json": None,
            "plan_json": None,
            "validation_json": None,
            "audit_jsonl": None,
            "artifact_bundle": row.get("artifact_storage"),
        },
        "metrics": {
            metric: _metric_value(metric, case={"status": observed_status, "evidence": row.get("evidence") or {}}, row=row)
            for metric in row.get("supports_metrics", [])
        },
        "inputs": row.get("inputs"),
        "notes": list(row.get("notes") or []),
        "evidence": dict(row.get("evidence") or {}),
        "evidence_paths": [
            _coerce_repo_relative(str(path), repo_root=repo_root)
            for path in row.get("evidence_paths", [])
        ],
        "analysis": row.get("analysis"),
    }


def build_freeze_report(*, repo_root: Path, spec_path: Path) -> dict[str, Any]:
    spec = _load_json(spec_path)
    rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []

    for row in spec.get("rows", []):
        if row.get("summary_kind") == "verification":
            frozen_row = _freeze_verification_row(row, repo_root=repo_root)
            rows.append(frozen_row)
            if frozen_row["expected_status"] != "passed" or frozen_row["observed_status"] != "passed":
                failure_rows.append(frozen_row)
            continue
        summary_rel = _coerce_repo_relative(str(row["summary_json"]), repo_root=repo_root)
        summary_payload = _load_json(repo_root / summary_rel)
        summary = _normalize_summary_payload(summary_payload)
        case_id = str(row["case_id"])
        case = next((item for item in summary["cases"] if item.get("case_id") == case_id), None)
        if case is None:
            raise ValueError(f"Case '{case_id}' not found in {summary_rel}")

        run_id = case.get("run_id")
        frozen_row = {
            "row_id": row["row_id"],
            "claim_ids": list(row.get("claim_ids") or []),
            "baseline": row["baseline"],
            "dataset": row["dataset"],
            "case_id": case_id,
            "case_name": case.get("case_name"),
            "expected_status": row.get("expected_status") or "passed",
            "observed_status": case.get("status"),
            "summary_json": summary_rel,
            "summary_source_format": summary["source_format"],
            "manifest": _coerce_repo_relative(summary.get("manifest"), repo_root=repo_root),
            "command": row["command"],
            "commit_sha": summary.get("commit_sha"),
            "base_url": summary.get("base_url"),
            "timeout_sec": case.get("timeout_sec", summary.get("timeout_sec")),
            "environment": dict(summary.get("environment") or {}),
            "run_id": run_id,
            "artifact_storage": row.get("artifact_storage"),
            "raw_artifacts": {
                "run_json": f"runs/{run_id}/run.json" if run_id else None,
                "plan_json": f"runs/{run_id}/plan.json" if run_id else None,
                "validation_json": f"runs/{run_id}/validation.json" if run_id else None,
                "audit_jsonl": f"runs/{run_id}/audit.jsonl" if run_id else None,
                "artifact_bundle": row.get("artifact_storage"),
            },
            "metrics": {
                metric: _metric_value(metric, case=case, row=row)
                for metric in row.get("supports_metrics", [])
            },
            "inputs": case.get("inputs"),
            "notes": case.get("notes"),
            "evidence": dict(case.get("evidence") or {}),
            "analysis": row.get("analysis"),
        }
        rows.append(frozen_row)
        if frozen_row["expected_status"] != "passed" or frozen_row["observed_status"] != "passed":
            failure_rows.append(frozen_row)

    qualitative_evidence = []
    for item in spec.get("qualitative_evidence", []):
        qualitative_evidence.append(
            {
                **item,
                "paths": [
                    _coerce_repo_relative(str(path), repo_root=repo_root)
                    for path in item.get("paths", [])
                ],
            }
        )

    return {
        "version": spec.get("version"),
        "spec_path": _coerce_repo_relative(str(spec_path), repo_root=repo_root),
        "rows": rows,
        "failure_rows": failure_rows,
        "qualitative_evidence": qualitative_evidence,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paper Evidence Freeze",
        "",
        "| Row | Claims | Baseline | Dataset | Observed Status | Summary |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["rows"]:
        summary_label = f"`{row['summary_json']}`" if row["summary_json"] else "verification evidence"
        lines.append(
            f"| {row['row_id']} | {', '.join(row['claim_ids'])} | {row['baseline']} | "
            f"{row['dataset']} | {row['observed_status']} | {summary_label} |"
        )

    lines.extend(["", "## Frozen Rows", ""])
    for row in report["rows"]:
        lines.append(f"### `{row['row_id']}`")
        lines.append("")
        lines.append(f"- Claims: {', '.join(row['claim_ids'])}")
        lines.append(f"- Baseline: {row['baseline']}")
        lines.append(f"- Dataset: {row['dataset']}")
        lines.append(f"- Observed status: {row['observed_status']}")
        if row.get("summary"):
            lines.append(f"- Summary: {row['summary']}")
        metrics = row.get("metrics") or {}
        if metrics:
            metric_summary = ", ".join(f"{name}={value}" for name, value in metrics.items())
            lines.append(f"- Metrics: {metric_summary}")
        if row.get("verification_command"):
            command = " ".join(str(part) for part in row["verification_command"])
            lines.append(f"- Verification command: `{command}`")
        if row.get("verification_result"):
            lines.append(f"- Verification result: {row['verification_result']}")
        evidence_paths = row.get("evidence_paths") or []
        if evidence_paths:
            lines.append(f"- Evidence paths: {', '.join(f'`{path}`' for path in evidence_paths)}")
        raw_artifacts = row.get("raw_artifacts") or {}
        available_artifacts = [f"{name}=`{value}`" for name, value in raw_artifacts.items() if value]
        if available_artifacts:
            lines.append(f"- Raw artifacts: {', '.join(available_artifacts)}")
        lines.append("")

    lines.extend(["", "## Failure Analysis", ""])
    if report["failure_rows"]:
        for row in report["failure_rows"]:
            lines.append(f"- `{row['row_id']}`: {row.get('analysis') or 'No analysis recorded.'}")
    else:
        lines.append("- No frozen failure rows.")

    lines.extend(["", "## Qualitative Evidence", ""])
    if report["qualitative_evidence"]:
        for item in report["qualitative_evidence"]:
            claims = ", ".join(item.get("claim_ids", []))
            paths = ", ".join(f"`{path}`" for path in item.get("paths", []))
            if paths:
                lines.append(f"- `{item['evidence_id']}` ({claims}): {item['summary']} Paths: {paths}")
            else:
                lines.append(f"- `{item['evidence_id']}` ({claims}): {item['summary']}")
    else:
        lines.append("- No qualitative evidence rows.")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze paper evidence from tracked experiment summaries.")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", required=True)
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    report = build_freeze_report(repo_root=repo_root, spec_path=Path(args.spec).resolve())

    output_json = Path(args.output_json).resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    output_markdown = Path(args.output_markdown).resolve()
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
