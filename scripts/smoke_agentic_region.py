from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Submit a task-driven natural-language region run and wait for the final result."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL.")
    parser.add_argument("--query", required=True, help="Natural-language region request.")
    parser.add_argument("--job-type", choices=["building", "road"], default="building", help="Fusion job type.")
    parser.add_argument("--target-crs", default="EPSG:32643", help="Target CRS for the run.")
    parser.add_argument("--timeout", type=float, default=1200.0, help="Overall timeout in seconds.")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Polling interval in seconds.")
    parser.add_argument("--output-json", default="", help="Optional path to save the final inspection payload.")
    return parser.parse_args(argv)


def build_create_run_form(args: argparse.Namespace) -> dict[str, str]:
    return {
        "job_type": args.job_type,
        "trigger_type": "user_query",
        "trigger_content": args.query,
        "target_crs": args.target_crs,
        "input_strategy": "task_driven_auto",
        "field_mapping": "{}",
        "debug": "false",
    }


def _json_request(
    method: str,
    url: str,
    *,
    form_data: dict[str, str] | None = None,
    timeout_sec: float = 30.0,
) -> Any:
    data = None
    headers: dict[str, str] = {}
    if form_data is not None:
        data = urllib.parse.urlencode(form_data).encode("utf-8")
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code} for {url}: {detail}") from exc


def _extract_event(events: list[dict[str, Any]], kind: str) -> dict[str, Any] | None:
    for event in events:
        if event.get("kind") == kind:
            return event
    return None


def run_smoke(
    *,
    base_url: str,
    query: str,
    job_type: str,
    target_crs: str,
    timeout_sec: float,
    poll_interval_sec: float,
) -> dict[str, Any]:
    create_url = urllib.parse.urljoin(base_url.rstrip("/") + "/", "api/v2/runs")
    create_payload = {
        "job_type": job_type,
        "trigger_type": "user_query",
        "trigger_content": query,
        "target_crs": target_crs,
        "input_strategy": "task_driven_auto",
        "field_mapping": "{}",
        "debug": "false",
    }
    created = _json_request("POST", create_url, form_data=create_payload, timeout_sec=min(timeout_sec, 60.0))
    run_id = created["run_id"]

    deadline = time.time() + timeout_sec
    status_url = urllib.parse.urljoin(base_url.rstrip("/") + "/", f"api/v2/runs/{run_id}")
    inspection_url = urllib.parse.urljoin(base_url.rstrip("/") + "/", f"api/v2/runs/{run_id}/inspection")

    while time.time() < deadline:
        status = _json_request("GET", status_url, timeout_sec=30.0)
        if status["phase"] == "failed":
            raise RuntimeError(f"Run failed: {status.get('error')}")
        if status["phase"] == "succeeded":
            inspection = _json_request("GET", inspection_url, timeout_sec=30.0)
            return {
                "run_id": run_id,
                "status": status,
                "inspection": inspection,
            }
        time.sleep(max(0.2, poll_interval_sec))
    raise TimeoutError(f"Timed out waiting for run {run_id}")


def _print_summary(result: dict[str, Any]) -> None:
    inspection = result["inspection"]
    audit_events = inspection.get("audit_events", [])
    aoi_event = _extract_event(audit_events, "aoi_resolved")
    source_event = _extract_event(audit_events, "task_inputs_resolved")
    artifact = inspection.get("artifact", {})

    print(f"run_id={result['run_id']}")
    print(f"phase={result['status']['phase']}")
    if aoi_event is not None:
        details = aoi_event.get("details", {})
        print(f"aoi={details.get('display_name')}")
        print(f"aoi_country={details.get('country_code')}")
    if source_event is not None:
        details = source_event.get("details", {})
        print(f"source_id={details.get('source_id')}")
        print(f"source_mode={details.get('source_mode')}")
    print(f"artifact_path={artifact.get('path')}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    result = run_smoke(
        base_url=args.base_url,
        query=args.query,
        job_type=args.job_type,
        target_crs=args.target_crs,
        timeout_sec=args.timeout,
        poll_interval_sec=args.poll_interval,
    )
    if args.output_json:
        output_path = Path(args.output_json).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result["inspection"], ensure_ascii=False, indent=2), encoding="utf-8")
    _print_summary(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
