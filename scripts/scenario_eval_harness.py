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
            passed = phase in case.expected_phase
            results.append(
                ScenarioHarnessCaseResult(
                    case_id=case.case_id,
                    scenario_id=response.scenario_id,
                    phase=phase,
                    passed=passed,
                    output_dir=response.output_dir,
                    expected_phase=list(case.expected_phase),
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
