from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def recover_summary(root: Path, *, source_commit: str) -> dict[str, Any]:
    result_paths = sorted((root / "runs").glob("*/result.json"))
    results = [json.loads(path.read_text(encoding="utf-8")) for path in result_paths]
    recovered_attempt_fields: list[dict[str, Any]] = []
    consumed_tokens = 0
    for result in results:
        attempt = result.get("attempt") or {}
        usage = attempt.get("usage")
        if not isinstance(usage, dict):
            raw_response = attempt.get("raw_response")
            try:
                raw_payload = json.loads(raw_response) if isinstance(raw_response, str) else {}
            except json.JSONDecodeError:
                raw_payload = {}
            usage = raw_payload.get("usage")
            recovered_attempt_fields.append(
                {
                    "run_id": result.get("run_id"),
                    "response_model": raw_payload.get("model"),
                    "finish_reason": ((raw_payload.get("choices") or [{}])[0]).get("finish_reason"),
                    "usage": usage,
                    "source": "attempt.raw_response",
                }
            )
        if isinstance(usage, dict) and isinstance(usage.get("total_tokens"), int):
            consumed_tokens += usage["total_tokens"]

    failures: dict[str, int] = {}
    for result in results:
        failure = result.get("failure_class")
        if failure:
            failures[str(failure)] = failures.get(str(failure), 0) + 1
    return {
        "status": "completed_with_observed_failures" if failures else "completed",
        "main_call_count": len(results),
        "successful_calls": sum(1 for result in results if result.get("success") is True),
        "failed_calls": sum(1 for result in results if result.get("success") is not True),
        "failure_counts": failures,
        "consumed_tokens": consumed_tokens,
        "source_commit": source_commit,
        "summary_recovery": {
            "reason": "original summary generation failed on null attempt usage",
            "raw_result_files_modified": False,
            "recovered_attempt_fields": recovered_attempt_fields,
        },
    }


def build_audit_manifest(root: Path) -> dict[str, Any]:
    files = []
    for path in sorted(item for item in root.rglob("*") if item.is_file() and item.name != "audit_manifest.json"):
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return {"algorithm": "sha256", "files": files}


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Recover a pilot summary without replaying provider calls.")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    args = parser.parse_args()

    _write_json(args.root / "pilot_summary.recovered.json", recover_summary(args.root, source_commit=args.source_commit))
    _write_json(
        args.root / "implementation_manifest.json",
        {
            "source_commit": args.source_commit,
            "working_tree": "clean detached worktree at execution time",
            "entrypoint": "scripts/run_research_llm_pilot.py",
        },
    )
    _write_json(args.root / "audit_manifest.json", build_audit_manifest(args.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
