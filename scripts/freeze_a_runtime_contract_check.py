from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from agent.tooling import build_default_tool_registry
from kg.inmemory_repository import InMemoryKGRepository
from kg.seed_manifest import build_seed_manifest_payload
from services.runtime_contract_service import RuntimeContractService


def build_report() -> dict[str, object]:
    repo = InMemoryKGRepository()
    registry = build_default_tool_registry()
    contract = RuntimeContractService(repo, tool_registry=registry)
    manifest = build_seed_manifest_payload()

    deprecated = [
        item
        for item in manifest["algorithms"]
        if (item.get("metadata") or {}).get("runtime_status") == "deprecated"
    ]
    deprecated_failures = []
    for item in deprecated:
        decision = contract.evaluate_algorithm(item["algo_id"], surface="freeze_a")
        metadata = item.get("metadata") or {}
        if decision.allowed or metadata.get("selectable_now") is not False:
            deprecated_failures.append({"algorithm_id": item["algo_id"], "decision": decision.to_dict()})

    registry_failures = []
    reserved_ids = {
        item["algo_id"]
        for item in manifest["algorithms"]
        if (item.get("metadata") or {}).get("runtime_status") == "reservation_only"
    }
    for algorithm_id in registry.list_algorithm_ids():
        if algorithm_id in reserved_ids:
            continue
        decision = contract.evaluate_algorithm(algorithm_id, surface="freeze_a")
        if not decision.allowed:
            registry_failures.append({"algorithm_id": algorithm_id, "decision": decision.to_dict()})

    pattern_failures = []
    for pattern in repo.list_workflow_patterns():
        decision = contract.evaluate_pattern(pattern, surface="freeze_a")
        if not decision.allowed:
            pattern_failures.append({"pattern_id": pattern.pattern_id, "decision": decision.to_dict()})

    report = {
        "seed_content_hash": manifest["metadata"]["content_hash"],
        "tool_registry_algorithm_ids": registry.list_algorithm_ids(),
        "validator_mode": {
            "default": os.getenv("GEOFUSION_VALIDATOR_MODE", "enforce"),
            "grounding_default": os.getenv("GEOFUSION_PLAN_GROUNDING_MODE", "enforce"),
        },
        "deprecated_algorithm_guard": {
            "ok": not deprecated_failures,
            "checked": [item["algo_id"] for item in deprecated],
            "failures": deprecated_failures,
        },
        "tool_registry_guard": {
            "ok": not registry_failures,
            "failures": registry_failures,
            "reserved_ids": sorted(reserved_ids),
        },
        "workflow_pattern_guard": {
            "ok": not pattern_failures,
            "failures": pattern_failures,
        },
    }
    report["ok"] = all(
        section["ok"]
        for section in [
            report["deprecated_algorithm_guard"],
            report["tool_registry_guard"],
            report["workflow_pattern_guard"],
        ]
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.parse_args()
    report = build_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
