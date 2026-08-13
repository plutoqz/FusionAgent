from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_research_llm_pilot import FORBIDDEN_PLANNER_KEYS, SYSTEM_PROMPT, _conservative_token_estimate, _nested_keys


def audit_preflight(
    *,
    manifest_path: Path,
    prepared_path: Path,
    prior_prepared_path: Path | None = None,
) -> dict[str, Any]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    leaks = []
    for item in prepared:
        leaked_keys = sorted(FORBIDDEN_PLANNER_KEYS & set(_nested_keys(item["payload"])))
        if leaked_keys:
            leaks.append({"run_id": item["schedule"]["run_id"], "keys": leaked_keys})

    prompt_bound = sum(_conservative_token_estimate(SYSTEM_PROMPT, item["payload"]) for item in prepared)
    result = {
        "status": "passed" if not leaks else "failed",
        "manifest_id": manifest["manifest_id"],
        "manifest_version": manifest["manifest_version"],
        "call_count": len(prepared),
        "unique_input_hashes": len({item["input_hash"] for item in prepared}),
        "forbidden_planner_keys": sorted(FORBIDDEN_PLANNER_KEYS),
        "leak_count": len(leaks),
        "leaks": leaks,
        "conservative_prompt_token_bound": prompt_bound,
        "conservative_batch_bounds": {
            "max_output_tokens_8192": prompt_bound + len(prepared) * 8192,
            "max_output_tokens_16384": prompt_bound + len(prepared) * 16384,
        },
    }
    if prior_prepared_path is not None:
        prior = json.loads(prior_prepared_path.read_text(encoding="utf-8"))
        prior_hashes = {item["schedule"]["run_id"]: item["input_hash"] for item in prior}
        result["prior_comparison"] = {
            "prior_prepared_path": prior_prepared_path.as_posix(),
            "changed_input_hashes": sum(
                prior_hashes.get(item["schedule"]["run_id"]) != item["input_hash"]
                for item in prepared
            ),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit research pilot preflight inputs for gold leakage.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--prepared", type=Path, required=True)
    parser.add_argument("--prior-prepared", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = audit_preflight(
        manifest_path=args.manifest,
        prepared_path=args.prepared,
        prior_prepared_path=args.prior_prepared,
    )
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
