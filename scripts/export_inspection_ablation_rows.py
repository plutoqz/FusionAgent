from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _event_kinds(inspection: dict[str, Any]) -> set[str]:
    events = inspection.get("audit_events")
    if not isinstance(events, list):
        return set()
    return {
        str(event.get("kind") or "")
        for event in events
        if isinstance(event, dict) and event.get("kind")
    }


def _plan_created_grounding_score(inspection: dict[str, Any]) -> float | None:
    events = inspection.get("audit_events")
    if not isinstance(events, list):
        return None
    for event in events:
        if not isinstance(event, dict) or event.get("kind") != "plan_created":
            continue
        details = event.get("details")
        if not isinstance(details, dict):
            continue
        value = details.get("grounding_score")
        if isinstance(value, int | float):
            return float(value)
    return None


def _walk_grounding_scores(value: Any) -> list[float]:
    scores: list[float] = []
    if isinstance(value, dict):
        score = value.get("grounding_score")
        if isinstance(score, int | float):
            scores.append(float(score))
        for child in value.values():
            scores.extend(_walk_grounding_scores(child))
    elif isinstance(value, list):
        for child in value:
            scores.extend(_walk_grounding_scores(child))
    return scores


def _grounding_score(inspection: dict[str, Any]) -> float:
    score = _plan_created_grounding_score(inspection)
    if score is not None:
        return score
    scores = _walk_grounding_scores(inspection)
    return float(scores[-1]) if scores else 0.0


def _validation_payload(inspection: dict[str, Any]) -> dict[str, Any]:
    direct = inspection.get("validation")
    if isinstance(direct, dict):
        return direct
    plan = inspection.get("plan")
    if isinstance(plan, dict) and isinstance(plan.get("validation"), dict):
        return dict(plan["validation"])
    return {}


def _unknown_algorithm_refs(validation: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    issues = validation.get("issues")
    if not isinstance(issues, list):
        return refs
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("code") or "")
        message = str(issue.get("message") or "")
        text = f"{code} {message}".upper()
        if "UNKNOWN_ALGORITHM" in text or "ALGORITHM_NOT_FOUND" in text:
            refs.append(code or message)
    return refs


def _kg_fallback_used(inspection: dict[str, Any]) -> bool:
    events = inspection.get("audit_events")
    if not isinstance(events, list):
        return False
    fallback_kinds = {"kg_fallback_used", "kg_fallback_applied", "plan_fallback_applied"}
    for event in events:
        if not isinstance(event, dict):
            continue
        if str(event.get("kind") or "") in fallback_kinds:
            return True
        details = event.get("details")
        if isinstance(details, dict) and details.get("kg_fallback_used") is True:
            return True
    return False


def extract_ablation_row(path: Path, *, variant: str = "A2c") -> dict[str, Any]:
    inspection = _load_json(path)
    run = inspection.get("run") if isinstance(inspection.get("run"), dict) else {}
    validation = _validation_payload(inspection)
    event_kinds = _event_kinds(inspection)
    artifact = run.get("artifact") if isinstance(run.get("artifact"), dict) else {}
    artifact_size = int(artifact.get("size_bytes") or 0)
    planning_valid = bool(validation.get("valid", "plan_validated" in event_kinds))
    execution_success = (
        run.get("phase") == "succeeded"
        and artifact_size > 0
        and "run_succeeded" in event_kinds
    )
    kg_fallback_used = _kg_fallback_used(inspection)

    return {
        "case_id": Path(path).stem,
        "variant": variant,
        "planning_valid": planning_valid,
        "unknown_algorithms": _unknown_algorithm_refs(validation),
        "execution_success": execution_success,
        "grounding_score": _grounding_score(inspection),
        "validator_rejected": not planning_valid,
        "kg_fallback_used": kg_fallback_used,
        "llm_plan_valid_before_fallback": planning_valid if not kg_fallback_used else False,
        "fallback_plan_quality_delta": 0.0,
        "run_id": run.get("run_id"),
        "job_type": run.get("job_type"),
        "phase": run.get("phase"),
        "artifact_size_bytes": artifact_size,
        "validation_issue_codes": [
            str(issue.get("code") or "")
            for issue in validation.get("issues", [])
            if isinstance(issue, dict) and issue.get("code")
        ]
        if isinstance(validation.get("issues"), list)
        else [],
        "source_inspection": str(Path(path)).replace("\\", "/"),
    }


def export_rows(paths: list[Path], *, variant: str, output_json: Path, output_markdown: Path | None = None) -> dict[str, Any]:
    rows = [extract_ablation_row(path, variant=variant) for path in paths]
    payload = {
        "source": "inspection-derived-ablation-input",
        "scope": "partial full-runtime slice; does not include A0/A1/A2b counterfactual variants",
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
        "# Inspection-Derived Ablation Rows",
        "",
        payload["scope"],
        "",
        "| Case | Variant | Job | Planning Valid | Execution Success | Grounding Score | Validator Rejected |",
        "| --- | --- | --- | --- | --- | ---: | --- |",
    ]
    for row in payload["rows"]:
        lines.append(
            "| {case_id} | {variant} | {job_type} | {planning_valid} | {execution_success} | {grounding_score} | {validator_rejected} |".format(
                **row
            )
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export eval_kg_ablation input rows from inspection payloads.")
    parser.add_argument("--input", action="append", required=True, help="Inspection JSON path.")
    parser.add_argument("--variant", default="A2c")
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", default="")
    args = parser.parse_args(argv)
    payload = export_rows(
        [Path(item) for item in args.input],
        variant=args.variant,
        output_json=Path(args.output_json),
        output_markdown=Path(args.output_markdown) if args.output_markdown else None,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
