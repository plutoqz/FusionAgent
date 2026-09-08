from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from benchmark_platform.canonical import canonical_sha256
from benchmark_platform.materializer import MemberMaterializerError, materialize_members, merge_v2_extension


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "docs/current/benchmark/v2/development_templates"
PROXY_ONLY_FAMILIES = {
    "TF-KG-CROSSWALK-MISSING": "proxy_resource_regime",
    "TF-PLAN-STRUCTURE-INVALID": "proxy_resource_regime",
    "TF-VALIDATOR-VETO": "proxy_resource_regime",
}


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def audit(package: Path = PACKAGE) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for base_path in sorted((package / "base").glob("TF-*.json")):
        base = _read(base_path)
        effective = base
        extension_path = package / "extensions" / base_path.name
        if extension_path.exists():
            effective = merge_v2_extension(base, _read(extension_path))
        unit = effective.get("experiment_unit", {})
        count = int(unit.get("minimum_members", 0)) if isinstance(unit, dict) else 0
        row: dict[str, Any] = {
            "template_family_id": base.get("template_family_id"),
            "unit_type": unit.get("unit_type") if isinstance(unit, dict) else None,
            "requested_members": count,
            "base_template_sha256": canonical_sha256(base),
            "extension_bound": effective is not base,
        }
        if row["template_family_id"] in PROXY_ONLY_FAMILIES:
            row.update({
                "status": "blocked_fail_closed",
                "member_count": 0,
                "distinct_member_count": 0,
                "member_hashes_valid": False,
                "failure_code": PROXY_ONLY_FAMILIES[row["template_family_id"]],
                "failure_message": "declared causal semantics are proxied through a v1 field; explicit v2 payload field is required",
            })
            rows.append(row)
            continue
        try:
            members = materialize_members(effective, count, seed=0)
            row.update({
                "status": "materializable",
                "member_count": len(members),
                "distinct_member_count": len({canonical_sha256(member) for member in members}),
                "member_hashes_valid": True,
            })
        except MemberMaterializerError as error:
            failure = error.failures[0]
            row.update({
                "status": "blocked_fail_closed",
                "member_count": 0,
                "distinct_member_count": 0,
                "member_hashes_valid": False,
                "failure_code": failure.details.get("code"),
                "failure_message": failure.message,
            })
        rows.append(row)
    materializable = sum(row["status"] == "materializable" for row in rows)
    return {
        "audit_id": "fusionagent.method-selection-development-member-materializer.v1",
        "status": "passed_with_semantic_blockers" if materializable != len(rows) else "passed",
        "package": package.relative_to(ROOT).as_posix(),
        "family_count": len(rows),
        "materializable_family_count": materializable,
        "blocked_family_count": len(rows) - materializable,
        "instances_generated": 0,
        "provider_calls": 0,
        "judge_calls": 0,
        "rows": rows,
        "evidence_boundary": {
            "materialization_is_in_memory_only": True,
            "live_gis_artifacts": False,
            "formal_experiment": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path, default=PACKAGE)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = audit(args.package)
    if args.output:
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("status", "family_count", "materializable_family_count", "blocked_family_count")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
