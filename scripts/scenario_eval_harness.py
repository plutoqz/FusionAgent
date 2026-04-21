from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from schemas.scenario import ScenarioRunRequest, ScenarioRunResponse
from schemas.scenario_manifest import ScenarioHarnessCaseResult, ScenarioHarnessSummary
from services.scenario_manifest_service import load_scenario_manifest, scenario_case_to_request


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


def run_manifest_cases(manifest_path: Path, output_root: Optional[str], client: Any) -> ScenarioHarnessSummary:
    manifest = load_scenario_manifest(manifest_path)
    results = []
    for case in manifest.cases:
        try:
            request = scenario_case_to_request(case, output_root=output_root)
            response = _coerce_scenario_response(client.create_scenario_run(request))
            phase = response.phase.value if hasattr(response.phase, "value") else str(response.phase)
            summary_path = Path(response.output_dir) / "scenario_summary.json"
            summary_payload = _load_summary(summary_path)
            observed = _build_observed_evidence(summary_payload)
            capability_failures = _capability_failures(case, observed)
            passed = phase in case.expected_phase and not capability_failures
            results.append(
                ScenarioHarnessCaseResult(
                    case_id=case.case_id,
                    scenario_id=response.scenario_id,
                    phase=phase,
                    passed=passed,
                    output_dir=response.output_dir,
                    summary_path=str(summary_path),
                    expected_phase=list(case.expected_phase),
                    capability_checks_passed=not capability_failures,
                    capability_failures=capability_failures,
                    observed=observed,
                    response=response.model_dump(mode="json"),
                )
            )
        except Exception as exc:  # noqa: BLE001
            results.append(
                ScenarioHarnessCaseResult(
                    case_id=case.case_id,
                    phase="failed",
                    passed=False,
                    expected_phase=list(case.expected_phase),
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    passed_cases = sum(1 for result in results if result.passed)
    failed_cases = len(results) - passed_cases
    return ScenarioHarnessSummary(
        manifest_id=manifest.manifest_id,
        total_cases=len(results),
        passed_cases=passed_cases,
        failed_cases=failed_cases,
        results=results,
        output_root=output_root,
        metadata=dict(manifest.metadata),
    )


def _coerce_scenario_response(response: Any) -> ScenarioRunResponse:
    if isinstance(response, ScenarioRunResponse):
        return response
    return ScenarioRunResponse.model_validate(response)


def _load_summary(summary_path: Path) -> dict[str, Any]:
    return json.loads(summary_path.read_text(encoding="utf-8"))


def _build_observed_evidence(summary: dict[str, Any]) -> dict[str, Any]:
    child_runs = summary.get("child_runs") or []
    workflow_traces = summary.get("workflow_traces") or []
    step_names = []
    observed_job_types = []
    for item in child_runs:
        if not isinstance(item, dict):
            continue
        job_type = str(item.get("job_type") or "").strip()
        if job_type and job_type not in observed_job_types:
            observed_job_types.append(job_type)
    for trace in workflow_traces:
        if not isinstance(trace, dict):
            continue
        for step in trace.get("steps", []):
            if not isinstance(step, dict):
                continue
            name = str(step.get("step_name") or "").strip()
            if name and name not in step_names:
                step_names.append(name)
    return {
        "observed_job_types": observed_job_types,
        "succeeded_child_count": sum(
            1
            for item in child_runs
            if isinstance(item, dict) and str(item.get("phase")) == "succeeded"
        ),
        "workflow_step_names": step_names,
        "source_coverage_count": len(summary.get("source_coverage") or []),
    }


def _capability_failures(case, observed: dict[str, Any]) -> list[str]:
    checks = case.capability_checks
    failures = []
    observed_job_types = set(observed.get("observed_job_types") or [])
    for job_type in checks.required_job_types:
        value = job_type.value if hasattr(job_type, "value") else str(job_type)
        if value not in observed_job_types:
            failures.append(f"required_job_types missing {value}")
    step_names = set(observed.get("workflow_step_names") or [])
    for step_name in checks.required_workflow_steps:
        if step_name not in step_names:
            failures.append(f"required_workflow_steps missing {step_name}")
    if observed.get("succeeded_child_count", 0) < checks.min_succeeded_children:
        failures.append(
            "min_succeeded_children expected "
            f"{checks.min_succeeded_children}, got {observed.get('succeeded_child_count', 0)}"
        )
    if checks.require_aoi_resolved and "aoi_resolved" not in step_names:
        failures.append("require_aoi_resolved missing aoi_resolved")
    if checks.require_task_inputs_resolved and "task_inputs_resolved" not in step_names:
        failures.append("require_task_inputs_resolved missing task_inputs_resolved")
    if checks.require_source_coverage and observed.get("source_coverage_count", 0) <= 0:
        failures.append("require_source_coverage missing source coverage evidence")
    return failures


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run scenario evaluation manifest cases through the scenario API.")
    parser.add_argument("--manifest", required=True, help="Scenario evaluation manifest JSON.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL.")
    parser.add_argument("--output-root", default=None, help="Scenario evidence output root.")
    parser.add_argument("--output-json", default="", help="Optional harness summary JSON output path.")
    parser.add_argument("--timeout", type=float, default=1200.0, help="Per-scenario API timeout in seconds.")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    client = HttpScenarioClient(base_url=args.base_url, timeout=args.timeout)
    summary = run_manifest_cases(Path(args.manifest), args.output_root, client)
    output = json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2)
    print(output)
    if args.output_json:
        output_path = Path(args.output_json)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output, encoding="utf-8")
    return 0 if summary.failed_cases == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
