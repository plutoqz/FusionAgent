from __future__ import annotations

import argparse
import json
import sys
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from schemas.engineering_validation import EngineeringValidationCase, EngineeringValidationCaseResult, EngineeringValidationSummary
from schemas.evidence_lifecycle import ValidationSessionManifest
from schemas.scenario import ScenarioRunRequest, ScenarioRunResponse
from services.evidence_lifecycle_service import write_validation_session_manifest


class HttpScenarioClient:
    def __init__(self, *, base_url: str, timeout: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = float(timeout)

    def create_scenario_run(self, request: ScenarioRunRequest) -> ScenarioRunResponse:
        response = httpx.post(
            f"{self.base_url}/api/v2/scenario-runs",
            json=request.model_dump(mode="json"),
            timeout=self.timeout,
        )
        response.raise_for_status()
        return ScenarioRunResponse.model_validate(response.json())


def load_matrix_cases(matrix_path: Path, selected_case_ids: list[str] | None = None) -> list[EngineeringValidationCase]:
    payload = json.loads(Path(matrix_path).read_text(encoding="utf-8"))
    raw_cases = payload.get("cases", [])
    selected = set(selected_case_ids or [])
    cases = [EngineeringValidationCase.model_validate(case) for case in raw_cases if isinstance(case, dict)]
    if selected:
        cases = [case for case in cases if case.case_id in selected]
    return cases


def case_to_scenario_request(case: EngineeringValidationCase, *, output_root: str | None) -> ScenarioRunRequest:
    return ScenarioRunRequest(
        scenario_name=case.scenario_name,
        trigger_content=f"{case.scenario_name}: {case.disaster_type} validation for {case.spatial_extent}",
        disaster_type=case.disaster_type,
        spatial_extent=case.spatial_extent,
        output_root=output_root,
        metadata={
            "case_id": case.case_id,
            "region_group": case.region_group,
            "aoi_class": case.aoi_class,
            "default_task_bundle": list(case.default_task_bundle),
            "engineering_validation": {
                "expected_task_kinds": list(case.expected_task_kinds),
                "expected_failed_children_max": case.expected_failed_children_max,
                "expected_quality_checks": list(case.expected_quality_checks),
                "degradation_mode": case.degradation_mode,
            },
            "quality_policy_id": case.quality_policy_id,
            "validation_runner": "engineering_validation",
        },
    )


def run_validation_cases(
    cases: list[EngineeringValidationCase],
    *,
    output_root: str | None,
    client: Any,
) -> list[EngineeringValidationCaseResult]:
    results: list[EngineeringValidationCaseResult] = []
    for case in cases:
        try:
            request = case_to_scenario_request(case, output_root=output_root)
            response = ScenarioRunResponse.model_validate(client.create_scenario_run(request))
            phase = response.phase.value if hasattr(response.phase, "value") else str(response.phase)
            summary_path = Path(response.output_dir) / "scenario_summary.json"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            passed, failures, observed = evaluate_case_summary(case, summary)
            results.append(
                EngineeringValidationCaseResult(
                    case_id=case.case_id,
                    passed=passed,
                    phase=phase,
                    scenario_id=response.scenario_id,
                    output_dir=response.output_dir,
                    summary_path=str(summary_path),
                    failure_reasons=failures,
                    observed=observed,
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                EngineeringValidationCaseResult(
                    case_id=case.case_id,
                    passed=False,
                    phase="failed",
                    failure_reasons=["runner_error"],
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
    return results


def evaluate_case_summary(
    case: EngineeringValidationCase,
    summary: dict[str, object],
) -> tuple[bool, list[str], dict[str, object]]:
    child_runs = summary.get("child_runs") if isinstance(summary.get("child_runs"), list) else []
    succeeded_children = [item for item in child_runs if isinstance(item, dict) and item.get("phase") == "succeeded"]
    observed_job_types = sorted(
        {
            str(item.get("job_type") or "")
            for item in child_runs
            if isinstance(item, dict) and str(item.get("job_type") or "").strip()
        }
    )
    observed_task_kinds = sorted(
        {
            str(item.get("task_kind") or "")
            for item in child_runs
            if isinstance(item, dict) and str(item.get("task_kind") or "").strip()
        }
    )
    observed_task_identifiers = sorted(
        {
            str(item.get("task_kind") or item.get("job_type") or "")
            for item in child_runs
            if isinstance(item, dict) and str(item.get("task_kind") or item.get("job_type") or "").strip()
        }
    )
    failures: list[str] = []
    phase = str(summary.get("phase") or "")
    if phase not in case.expected_phase:
        failures.append(f"phase expected one of {case.expected_phase}, got {phase}")
    if len(succeeded_children) < case.expected_min_succeeded_children:
        failures.append(
            f"succeeded children expected at least {case.expected_min_succeeded_children}, got {len(succeeded_children)}"
        )
    missing_tasks = [task for task in case.expected_required_tasks if task not in observed_job_types]
    if missing_tasks:
        failures.append(f"missing required job types: {missing_tasks}")
    quality = summary.get("quality") if isinstance(summary.get("quality"), dict) else {}
    failed_children = summary.get("failed_children") if isinstance(summary.get("failed_children"), list) else []
    missing_task_kinds = [task_kind for task_kind in case.expected_task_kinds if task_kind not in observed_task_kinds]
    if missing_task_kinds:
        failures.append(f"missing expected task kinds: {missing_task_kinds}")
    if case.expected_failed_children_max is not None and len(failed_children) > case.expected_failed_children_max:
        failures.append(
            f"failed children expected at most {case.expected_failed_children_max}, got {len(failed_children)}"
        )
    quality_check_details = {
        check_name: _quality_check_detail(quality, check_name) for check_name in case.expected_quality_checks
    }
    quality_checks = {check_name: detail["passed"] for check_name, detail in quality_check_details.items()}
    missing_quality_checks = [
        f"{check_name}@{child_ref}"
        for check_name, detail in quality_check_details.items()
        for child_ref in detail["missing"]
    ]
    failing_quality_checks = [
        f"{check_name}@{child_ref}"
        for check_name, detail in quality_check_details.items()
        for child_ref in detail["failed"]
    ]
    if missing_quality_checks:
        failures.append(f"missing quality checks: {missing_quality_checks}")
    if failing_quality_checks:
        failures.append(f"quality checks not passing: {failing_quality_checks}")
    observed = {
        "phase": phase,
        "region_group": case.region_group,
        "aoi_class": case.aoi_class,
        "observed_tasks": observed_task_kinds,
        "observed_job_types": observed_job_types,
        "observed_task_kinds": observed_task_kinds,
        "observed_task_identifiers": observed_task_identifiers,
        "succeeded_child_count": len(succeeded_children),
        "failed_child_count": len(failed_children),
        "degradation_mode": case.degradation_mode,
        "quality_checks": quality_checks,
        "quality_check_details": quality_check_details,
        "quality": quality,
    }
    return not failures, failures, observed


def _quality_check_detail(quality: dict[str, object], check_name: str) -> dict[str, object]:
    child_reports = quality.get("child_reports") if isinstance(quality.get("child_reports"), list) else []
    if child_reports:
        missing: list[str] = []
        failed: list[str] = []
        seen = False
        for index, report in enumerate(child_reports):
            if not isinstance(report, dict):
                continue
            child_ref = _quality_child_ref(report, index)
            report_checks = report.get("checks") if isinstance(report.get("checks"), dict) else {}
            if check_name not in report_checks:
                missing.append(child_ref)
                continue
            seen = True
            if not _quality_check_value_passed(report_checks[check_name]):
                failed.append(child_ref)
        return {"passed": bool(seen) and not missing and not failed, "missing": missing, "failed": failed}

    checks = quality.get("checks") if isinstance(quality.get("checks"), dict) else {}
    if check_name in checks:
        passed = _quality_check_value_passed(checks[check_name])
        return {"passed": passed, "missing": [], "failed": [] if passed else ["summary"]}
    if check_name in quality:
        passed = _quality_check_value_passed(quality[check_name])
        return {"passed": passed, "missing": [], "failed": [] if passed else ["summary"]}
    return {"passed": None, "missing": ["summary"], "failed": []}


def _quality_child_ref(report: dict[str, object], index: int) -> str:
    run_id = str(report.get("run_id") or "").strip()
    if run_id:
        return run_id
    for key in ("task_kind", "policy_id"):
        value = str(report.get(key) or "").strip()
        if value:
            return f"{value}#{index + 1}"
    return f"child-{index + 1}"


def _quality_check_value_passed(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        if isinstance(value.get("passed"), bool):
            return bool(value["passed"])
        if isinstance(value.get("accepted"), bool):
            return bool(value["accepted"])
        status = str(value.get("status") or "").strip().lower()
        return status in {"passed", "pass", "ok", "accepted", "succeeded", "success"}
    if isinstance(value, str):
        return value.strip().lower() in {"passed", "pass", "ok", "accepted", "succeeded", "success"}
    return False


def write_validation_outputs(
    *,
    session_id: str,
    matrix_path: Path,
    output_root: Path,
    cases: list[EngineeringValidationCase],
    results: list[EngineeringValidationCaseResult],
    metadata: dict[str, Any] | None = None,
) -> EngineeringValidationSummary:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    metadata = dict(metadata or {})
    matrix_payload = json.loads(Path(matrix_path).read_text(encoding="utf-8")) if Path(matrix_path).exists() else {}
    (output_root / "matrix_snapshot.json").write_text(
        json.dumps(matrix_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_root / "case_results.jsonl").write_text(
        "".join(json.dumps(result.model_dump(mode="json"), ensure_ascii=False) + "\n" for result in results),
        encoding="utf-8",
    )
    passed_cases = sum(1 for result in results if result.passed)
    summary = EngineeringValidationSummary(
        session_id=session_id,
        matrix_path=str(matrix_path),
        total_cases=len(results),
        passed_cases=passed_cases,
        failed_cases=len(results) - passed_cases,
        results=results,
        output_root=str(output_root),
        metadata={**metadata, "case_count": len(cases)},
    )
    (output_root / "validation_summary.json").write_text(
        json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_root / "validation_summary.md").write_text(
        _render_validation_markdown(results),
        encoding="utf-8",
    )
    manifest = ValidationSessionManifest(
        session_id=session_id,
        matrix_path=str(matrix_path),
        output_root=str(output_root),
        case_result_paths=["case_results.jsonl"],
        summary_path="validation_summary.json",
        markdown_summary_path="validation_summary.md",
        created_at=datetime.now(timezone.utc).isoformat(),
        git_commit=_git_commit(),
        runtime=metadata,
    )
    write_validation_session_manifest(output_root / "validation_session.json", manifest)
    return summary


def _render_validation_markdown(results: list[EngineeringValidationCaseResult]) -> str:
    lines = [
        "# Engineering Validation Summary",
        "",
        "| Case | Region | AOI | Phase | Passed | Failures |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        observed = result.observed if isinstance(result.observed, dict) else {}
        failures = "; ".join(result.failure_reasons)
        lines.append(
            "| "
            + " | ".join(
                [
                    result.case_id,
                    str(observed.get("region_group") or ""),
                    str(observed.get("aoi_class") or ""),
                    result.phase,
                    "yes" if result.passed else "no",
                    failures,
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:  # noqa: BLE001
        return None
    return completed.stdout.strip()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", default="docs/superpowers/validation/engineering_validation_matrix.yaml")
    parser.add_argument("--case", action="append", default=[], help="Case id to run. Can be passed multiple times.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-root", default="")
    parser.add_argument("--timeout", type=float, default=1200.0)
    parser.add_argument("--session-id", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    matrix_path = Path(args.matrix)
    try:
        cases = load_matrix_cases(matrix_path, selected_case_ids=args.case)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to load matrix: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if args.case and not cases:
        print(f"No selected cases found: {', '.join(args.case)}", file=sys.stderr)
        return 2
    for case in cases:
        print(f"{case.case_id}: {case.scenario_name} [{case.aoi_class}]")
    if args.dry_run:
        return 0
    session_id = args.session_id or datetime.now().strftime("validation-%Y%m%d-%H%M%S")
    output_root = Path(args.output_root) if args.output_root else REPO_ROOT / "runs" / "engineering-validation" / session_id
    client = HttpScenarioClient(base_url=args.base_url, timeout=args.timeout)
    results = run_validation_cases(cases, output_root=str(output_root), client=client)
    summary = write_validation_outputs(
        session_id=session_id,
        matrix_path=matrix_path,
        output_root=output_root,
        cases=cases,
        results=results,
        metadata={"base_url": args.base_url, "timeout": args.timeout},
    )
    print(f"Validation summary: {output_root / 'validation_summary.json'}")
    return 0 if summary.failed_cases == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
