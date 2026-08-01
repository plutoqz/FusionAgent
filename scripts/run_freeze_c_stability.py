from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


STABILITY_ID = "fusionagent.freeze-c-stability.v1"
REPORT_SCHEMA_VERSION = "1.0.0"
VOLATILE_KEYS = {
    "artifact_id",
    "artifact_path",
    "created_at",
    "experiment_dir",
    "finished_at",
    "manifest_path",
    "path",
    "run_id",
    "runtime_summary_path",
    "scenario_id",
    "started_at",
    "summary_path",
    "timestamp",
    "updated_at",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_run_snapshot(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    result = _load_json(run_dir / "experiment_result.json")
    cases: list[dict[str, Any]] = []
    for case_dir in sorted((run_dir / "cases").iterdir()):
        if not case_dir.is_dir():
            continue
        cases.append(_case_snapshot(case_dir))

    artifact_hashes = _artifact_hashes(run_dir, cases)
    external_input_hashes = _external_input_hashes(run_dir)
    prepared_input_hashes = [
        {
            "case_id": case_dir.name,
            "filename": path.name,
            "sha256": sha256_file(path),
            "size_bytes": path.stat().st_size,
            "semantic_sha256": _json_hash(_stable_value(_load_json(path))),
        }
        for case_dir in sorted((run_dir / "cases").iterdir())
        if case_dir.is_dir()
        for path in sorted(case_dir.glob("prepared_inputs_*.json"))
    ]
    return {
        "experiment_id": result.get("experiment_id"),
        "all_cases_passed": result.get("all_cases_passed"),
        "case_count": len(cases),
        "cases": cases,
        "artifact_hashes": artifact_hashes,
        "external_input_hashes": external_input_hashes,
        "prepared_input_hashes": prepared_input_hashes,
    }


def compare_snapshots(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    if not snapshots:
        raise ValueError("至少需要一个运行快照")
    byte_values = [
        {
            "artifact_hashes": item["artifact_hashes"],
            "external_input_hashes": item["external_input_hashes"],
        }
        for item in snapshots
    ]
    semantic_values = [_semantic_snapshot(item) for item in snapshots]
    byte_differences = _differences(byte_values)
    semantic_differences = _differences(semantic_values)
    allowed_fluctuations = _classify_allowed_byte_fluctuations(snapshots, byte_differences)
    return {
        "run_count": len(snapshots),
        "byte_level": {
            "stable": not byte_differences,
            "compared_fields": ["artifact_hashes", "external_input_hashes"],
            "differences": byte_differences,
        },
        "semantic_level": {
            "stable": not semantic_differences,
            "compared_fields": [
                "all_cases_passed",
                "case stages",
                "feature counts",
                "coverage counts",
                "quality metrics",
                "gap declarations",
                "prepared-input semantic hashes",
                "task order",
                "supersession topology",
            ],
            "differences": semantic_differences,
        },
        "allowed_fluctuations": {
            "fields": sorted(VOLATILE_KEYS),
            "excluded_from_semantic_comparison": True,
            "classified_byte_differences": allowed_fluctuations["classified"],
            "unclassified_byte_differences": allowed_fluctuations["unclassified"],
            "notes": [
                "run_id/scenario_id/artifact_id and absolute paths are execution identities, not semantic outputs",
                "timestamps and runtime metadata are reported per run but are not stability claims",
                "ZIP container bytes may vary while canonical member-content hashes remain stable",
            ],
        },
    }


def run_stability(
    *,
    worktree: Path,
    evidence_root: Path,
    python_executable: Path,
    manifest_path: Path | None = None,
    run_count: int = 3,
    server_port: int = 8219,
    timeout_seconds: float = 1800.0,
) -> dict[str, Any]:
    worktree = Path(worktree).resolve()
    evidence_root = Path(evidence_root).resolve()
    manifest_path = Path(manifest_path or worktree / "docs/thesis/manifests/2026-07-20-c02-c04-c06-real-data.json").resolve()
    if run_count < 3:
        raise ValueError("P2 至少需要三次运行")
    _assert_new_directory(evidence_root)
    evidence_root.mkdir(parents=True, exist_ok=True)

    commit_sha = _git_output(worktree, "rev-parse", "HEAD")
    manifest = _load_json(manifest_path)
    fixed_environment = dict(manifest.get("runtime") or {})
    fixed_environment.update(_fixed_environment())
    snapshots: list[dict[str, Any]] = []
    runs: list[dict[str, Any]] = []
    runner = worktree / "scripts/run_contract_case_experiments.py"
    for index in range(1, run_count + 1):
        run_dir = evidence_root / f"run-{index:02d}"
        command = [
            str(python_executable),
            str(runner),
            "--manifest",
            str(manifest_path),
            "--experiment-dir",
            str(run_dir),
            "--server-port",
            str(server_port),
            "--timeout-seconds",
            str(timeout_seconds),
        ]
        environment = os.environ.copy()
        environment.update({key: str(value) for key, value in fixed_environment.items()})
        environment["PYTHONPATH"] = str(worktree) + os.pathsep + environment.get("PYTHONPATH", "")
        completed = subprocess.run(
            command,
            cwd=worktree,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        run_record = {
            "run_index": index,
            "run_dir": str(run_dir),
            "returncode": completed.returncode,
            "command": command,
        }
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "p2_runner.stdout.log").write_text(completed.stdout, encoding="utf-8")
        (run_dir / "p2_runner.stderr.log").write_text(completed.stderr, encoding="utf-8")
        if completed.returncode != 0 or not (run_dir / "experiment_result.json").is_file():
            run_record["passed"] = False
            runs.append(run_record)
            return _report(
                worktree=worktree,
                evidence_root=evidence_root,
                manifest_path=manifest_path,
                commit_sha=commit_sha,
                fixed_environment=fixed_environment,
                runs=runs,
                snapshots=snapshots,
                comparison=None,
            )
        snapshot = build_run_snapshot(run_dir)
        run_record.update({"passed": snapshot["all_cases_passed"] is True, "snapshot": snapshot})
        runs.append(run_record)
        snapshots.append(snapshot)

    comparison = compare_snapshots(snapshots)
    report = _report(
        worktree=worktree,
        evidence_root=evidence_root,
        manifest_path=manifest_path,
        commit_sha=commit_sha,
        fixed_environment=fixed_environment,
        runs=runs,
        snapshots=snapshots,
        comparison=comparison,
    )
    _write_new_file(evidence_root / "p2_stability_report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


def analyze_existing_stability(
    *,
    worktree: Path,
    evidence_root: Path,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    worktree = Path(worktree).resolve()
    evidence_root = Path(evidence_root).resolve()
    manifest_path = Path(manifest_path or worktree / "docs/thesis/manifests/2026-07-20-c02-c04-c06-real-data.json").resolve()
    run_dirs = sorted(path for path in evidence_root.glob("run-[0-9][0-9]") if path.is_dir())
    if len(run_dirs) < 3:
        raise ValueError("已有 P2 证据目录少于三次运行")
    snapshots = [build_run_snapshot(path) for path in run_dirs]
    runs = [
        {
            "run_index": index,
            "run_dir": str(path),
            "returncode": 0 if snapshot.get("all_cases_passed") is True else 1,
            "passed": snapshot.get("all_cases_passed") is True,
            "snapshot": snapshot,
        }
        for index, (path, snapshot) in enumerate(zip(run_dirs, snapshots), start=1)
    ]
    manifest = _load_json(manifest_path)
    fixed_environment = dict(manifest.get("runtime") or {})
    fixed_environment.update(_fixed_environment())
    return _report(
        worktree=worktree,
        evidence_root=evidence_root,
        manifest_path=manifest_path,
        commit_sha=_git_output(worktree, "rev-parse", "HEAD"),
        fixed_environment=fixed_environment,
        runs=runs,
        snapshots=snapshots,
        comparison=compare_snapshots(snapshots),
    )


def render_summary(report: dict[str, Any]) -> str:
    comparison = report.get("comparison") or {}
    byte_level = comparison.get("byte_level") or {}
    semantic_level = comparison.get("semantic_level") or {}
    allowed = comparison.get("allowed_fluctuations") or {}
    lines = [
        "# Freeze C P2 稳定性重跑摘要",
        "",
        f"- 总体结果：**{'通过' if report['passed'] else '失败'}**",
        f"- commit：`{report['commit_sha']}`",
        f"- 运行次数：{report['run_count']}",
        f"- 字节级稳定：**{'是' if byte_level.get('stable') else '否'}**",
        f"- 语义级稳定：**{'是' if semantic_level.get('stable') else '否'}**",
        f"- 未解释字节差异：**{len(allowed.get('unclassified_byte_differences') or [])}**",
        "",
        "## 运行状态",
        "",
    ]
    for item in report["runs"]:
        lines.append(f"- Run {item['run_index']:02d}：{'通过' if item.get('passed') else '失败'}，退出码 `{item['returncode']}`，目录 `{item['run_dir']}`")
    if allowed.get("classified_byte_differences"):
        lines.extend(["", "## 允许波动分类", ""])
        lines.extend(f"- `{item}`" for item in allowed["classified_byte_differences"])
    lines.extend(["", "## 比较范围", ""])
    lines.append("- 字节级：artifact 原始 SHA-256、9 组/32 个外部输入 SHA-256")
    lines.append("- 语义级：以下字段")
    for field in semantic_level.get("compared_fields", []):
        lines.append(f"- {field}")
    if byte_level.get("differences"):
        lines.extend(["", "## 字节级差异", ""])
        lines.extend(f"- `{item}`" for item in byte_level["differences"][:20])
    if semantic_level.get("differences"):
        lines.extend(["", "## 语义级差异", ""])
        lines.extend(f"- `{item}`" for item in semantic_level["differences"][:20])
    lines.extend(
        [
            "",
            "允许波动：run/scenario/artifact 标识、绝对路径、时间戳和运行元数据不参与语义稳定判定；它们仍保留在各次原始运行目录中。",
            "",
        ]
    )
    return "\n".join(lines)


def write_summary(report: dict[str, Any], path: Path) -> None:
    _write_new_file(Path(path), render_summary(report))


def _case_snapshot(case_dir: Path) -> dict[str, Any]:
    case_result = _load_json(case_dir / "case_result.json")
    planning = _load_json(case_dir / "planning_decision.json")
    gaps = _load_json(case_dir / "gap_declaration.json")
    delivery = _load_json(case_dir / "delivery_manifest.json")
    quality = _load_json(case_dir / "quality_gate_result.json")
    return {
        "case_id": case_result.get("case_id"),
        "passed": case_result.get("passed"),
        "final_phase": case_result.get("final_phase"),
        "final_task_order": case_result.get("final_task_order"),
        "gap_count": case_result.get("gap_count"),
        "assertions": case_result.get("assertions"),
        "stages": [
            {
                "stage_id": item.get("stage_id"),
                "phase": item.get("phase"),
                "task_order": item.get("task_order"),
                "base_assertions": item.get("base_assertions"),
                "declared_assertions": item.get("declared_assertions"),
                "observations": item.get("observations"),
                "passed": item.get("passed"),
            }
            for item in case_result.get("stage_evaluations", [])
        ],
        "planning": {
            "expected_layer_priority": planning.get("expected_layer_priority"),
            "actual_task_order": planning.get("actual_task_order"),
            "decision": planning.get("decision"),
        },
        "gaps": [
            {
                "layer": item.get("layer"),
                "gap_type": item.get("gap_type"),
                "source_ids": item.get("source_ids"),
                "phase": item.get("phase"),
                "stage_id": item.get("stage_id"),
            }
            for item in gaps.get("observed_gaps", [])
        ],
        "delivery": _delivery_snapshot(delivery),
        "quality": _quality_snapshot(quality),
    }


def _delivery_snapshot(delivery: dict[str, Any]) -> dict[str, Any]:
    return {
        "final_phase": delivery.get("final_phase"),
        "output_count": len(delivery.get("outputs") or []),
        "provisional": sorted(
            [
                {
                    "task_kind": item.get("task_kind"),
                    "task_family": item.get("task_family"),
                    "phase": item.get("phase"),
                    "provisional": item.get("provisional"),
                    "fusion_mode": item.get("fusion_mode"),
                    "missing_sources": item.get("missing_sources"),
                    "stage_id": item.get("_experiment_stage_id"),
                }
                for item in delivery.get("provisional_outputs") or []
            ],
            key=lambda item: json.dumps(item, sort_keys=True),
        ),
        "superseded": sorted(
            [
                {
                    "task_kind": item.get("task_kind"),
                    "phase": item.get("phase"),
                    "relation_present": bool(item.get("superseded_by")),
                }
                for item in delivery.get("superseded_outputs") or []
            ],
            key=lambda item: json.dumps(item, sort_keys=True),
        ),
    }


def _quality_snapshot(quality: dict[str, Any]) -> dict[str, Any]:
    return {
        "case_id": quality.get("case_id"),
        "accepted_child_count": quality.get("accepted_child_count"),
        "rejected_child_count": quality.get("rejected_child_count"),
        "final_phase": quality.get("final_phase"),
        "stages": [
            {
                "stage_id": stage.get("stage_id"),
                "phase": stage.get("phase"),
                "accepted_child_count": stage.get("accepted_child_count"),
                "rejected_child_count": stage.get("rejected_child_count"),
                "child_reports": [
                    {
                        "task_kind": child.get("task_kind"),
                        "accepted": child.get("accepted"),
                        "metrics": child.get("metrics"),
                        "raw_quality_passed": child.get("raw_quality_passed"),
                        "adapted_quality_passed": child.get("adapted_quality_passed"),
                        "degraded_mode": child.get("degraded_mode"),
                        "degradation_level": child.get("degradation_level"),
                    }
                    for child in stage.get("child_reports", [])
                ],
            }
            for stage in quality.get("stages", [])
        ],
        "child_reports": [
            {
                "task_kind": child.get("task_kind"),
                "accepted": child.get("accepted"),
                "metrics": child.get("metrics"),
                "raw_quality_passed": child.get("raw_quality_passed"),
                "adapted_quality_passed": child.get("adapted_quality_passed"),
                "degraded_mode": child.get("degraded_mode"),
                "degradation_level": child.get("degradation_level"),
            }
            for child in quality.get("child_reports", [])
        ],
    }


def _artifact_hashes(run_dir: Path, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for case_dir in sorted((run_dir / "cases").iterdir()):
        if not case_dir.is_dir():
            continue
        delivery = _load_json(case_dir / "delivery_manifest.json")
        for collection in ("outputs", "provisional_outputs", "superseded_outputs"):
            values = delivery.get(collection) or []
            if collection == "outputs":
                values = [{"artifact_path": value, "task_kind": None, "phase": delivery.get("final_phase")} for value in values]
            for item in values:
                artifact_path = Path(str(item.get("artifact_path") or ""))
                if not artifact_path.is_file():
                    continue
                task_kind = item.get("task_kind") or _task_kind_for_artifact(artifact_path)
                records.append(
                    {
                        "case_id": case_dir.name,
                        "collection": collection,
                        "task_kind": task_kind,
                        "phase": item.get("phase"),
                        "filename": artifact_path.name,
                        "sha256": sha256_file(artifact_path),
                        "content_sha256": _artifact_content_hash(artifact_path),
                        "size_bytes": artifact_path.stat().st_size,
                    }
                )
    return sorted(records, key=lambda item: json.dumps(item, sort_keys=True))


def _external_input_hashes(run_dir: Path) -> list[dict[str, Any]]:
    manifest_path = run_dir / "experiment_evidence_manifest.json"
    if not manifest_path.is_file():
        return []
    manifest = _load_json(manifest_path)
    records = []
    for source in manifest.get("external_inputs") or []:
        for item in source.get("files") or []:
            records.append(
                {
                    "source_id": source.get("source_id"),
                    "filename": Path(str(item.get("path") or "")).name,
                    "sha256": item.get("sha256"),
                    "size_bytes": item.get("size_bytes"),
                }
            )
    return sorted(records, key=lambda item: json.dumps(item, sort_keys=True))


def _task_kind_for_artifact(artifact_path: Path) -> str | None:
    run_dir = artifact_path.parent.parent
    run = _load_json(run_dir / "run.json") if (run_dir / "run.json").is_file() else {}
    plan = _load_json(run_dir / "plan.json") if (run_dir / "plan.json").is_file() else {}
    task = (plan.get("tasks") or [{}])[0]
    text = " ".join(str(task.get(key) or "") for key in ("task_kind", "name", "algorithm_id"))
    for task_kind in ("water_polygon", "waterways", "road", "building", "poi"):
        if task_kind in text:
            return task_kind
    return str(run.get("job_type") or "") or None


def _semantic_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    artifacts = [
        {
            key: item[key]
            for key in ("case_id", "collection", "task_kind", "phase", "filename", "content_sha256")
            if key in item
        }
        for item in snapshot["artifact_hashes"]
    ]
    return _stable_value(
        {
            key: value
            for key, value in snapshot.items()
            if key not in {"artifact_hashes", "external_input_hashes", "prepared_input_hashes"}
        }
        | {"artifact_content_hashes": artifacts}
    )


def _json_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _artifact_content_hash(path: Path) -> str:
    if path.suffix.casefold() != ".zip":
        return sha256_file(path)
    import zipfile

    members = []
    try:
        with zipfile.ZipFile(path) as archive:
            for info in sorted(archive.infolist(), key=lambda item: item.filename):
                data = archive.read(info)
                members.append(
                    {
                        "filename": info.filename,
                        "size_bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
    except zipfile.BadZipFile:
        return sha256_file(path)
    return _json_hash(members)


def _classify_allowed_byte_fluctuations(
    snapshots: list[dict[str, Any]], byte_differences: list[str]
) -> dict[str, list[str]]:
    records_by_run = [
        {
            (
                item.get("case_id"),
                item.get("collection"),
                item.get("task_kind"),
                item.get("phase"),
                item.get("filename"),
            ): item
            for item in snapshot["artifact_hashes"]
        }
        for snapshot in snapshots
    ]
    all_keys = set().union(*(records.keys() for records in records_by_run))
    classified: list[str] = []
    unclassified: list[str] = []
    for key in sorted(all_keys, key=str):
        records = [records_by_run[0].get(key)] + [records.get(key) for records in records_by_run[1:]]
        if any(record is None for record in records):
            unclassified.append(f"artifact identity missing across runs: {key}")
            continue
        raw_hashes = {record["sha256"] for record in records}
        content_hashes = {record["content_sha256"] for record in records}
        if len(raw_hashes) > 1 and len(content_hashes) == 1:
            classified.append(f"ZIP/container bytes vary but member content is stable: {key}")
        elif len(raw_hashes) > 1:
            unclassified.append(f"artifact content changed: {key}")
    unclassified.extend(
        difference
        for difference in byte_differences
        if ".artifact_hashes" not in difference
    )
    return {"classified": classified, "unclassified": list(dict.fromkeys(unclassified))}


def _stable_value(value: Any, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {
            item_key: _stable_value(item_value, item_key)
            for item_key, item_value in sorted(value.items())
            if not _is_volatile_key(item_key)
        }
    if isinstance(value, list):
        return [_stable_value(item, key) for item in value]
    if isinstance(value, str) and key and (key.endswith("_path") or key == "path"):
        return "<path>"
    return value


def _is_volatile_key(key: str) -> bool:
    return key in VOLATILE_KEYS or key.endswith("_path")


def _differences(values: list[Any]) -> list[str]:
    baseline = values[0]
    differences: list[str] = []
    for index, value in enumerate(values[1:], start=2):
        differences.extend(_diff_values(baseline, value, path=f"run-01 vs run-{index:02d}"))
    return differences


def _diff_values(left: Any, right: Any, *, path: str) -> list[str]:
    if type(left) is not type(right):
        return [f"{path}: type {type(left).__name__} != {type(right).__name__}"]
    if isinstance(left, dict):
        differences: list[str] = []
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                differences.append(f"{path}.{key}: missing on one side")
            else:
                differences.extend(_diff_values(left[key], right[key], path=f"{path}.{key}"))
        return differences
    if isinstance(left, list):
        differences = []
        if len(left) != len(right):
            differences.append(f"{path}: length {len(left)} != {len(right)}")
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            differences.extend(_diff_values(left_item, right_item, path=f"{path}[{index}]"))
        return differences
    return [] if left == right else [f"{path}: {left!r} != {right!r}"]


def _report(
    *,
    worktree: Path,
    evidence_root: Path,
    manifest_path: Path,
    commit_sha: str,
    fixed_environment: dict[str, Any],
    runs: list[dict[str, Any]],
    snapshots: list[dict[str, Any]],
    comparison: dict[str, Any] | None,
) -> dict[str, Any]:
    run_success = len(runs) == len(snapshots) and all(item.get("passed") is True for item in runs)
    comparison_passed = (
        comparison is not None
        and comparison["semantic_level"]["stable"]
        and not comparison["allowed_fluctuations"]["unclassified_byte_differences"]
    )
    return {
        "stability_id": STABILITY_ID,
        "schema_version": REPORT_SCHEMA_VERSION,
        "passed": run_success and comparison_passed,
        "commit_sha": commit_sha,
        "worktree": str(worktree),
        "manifest_path": str(manifest_path),
        "evidence_root": str(evidence_root),
        "run_count": len(runs),
        "fixed_environment": fixed_environment,
        "runs": runs,
        "comparison": comparison,
    }


def _assert_new_directory(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise FileExistsError(f"P2 证据目录非空，拒绝覆盖: {path}")


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON 顶层必须是 object: {path}")
    return payload


def _git_output(worktree: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=worktree, text=True).strip()


def _write_new_file(path: Path, content: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="") as handle:
        handle.write(content)


def _fixed_environment() -> dict[str, str]:
    return {
        "GEOFUSION_KG_BACKEND": "memory",
        "GEOFUSION_LLM_PROVIDER": "mock",
        "GEOFUSION_CELERY_EAGER": "1",
        "GEOFUSION_SCENARIO_CHILD_MAX_WORKERS": "1",
        "GEOFUSION_LOCAL_ONLY": "1",
        "GEOFUSION_DISABLE_ARTIFACT_REUSE": "1",
        "PYTHONUTF8": "1",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="在冻结 commit 和固定环境下重复运行 Freeze C 并比较稳定性。")
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--evidence-root", required=True)
    parser.add_argument("--python-executable", default=sys.executable)
    parser.add_argument("--manifest", default="")
    parser.add_argument("--run-count", type=int, default=3)
    parser.add_argument("--server-port", type=int, default=8219)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument("--reuse-existing", action="store_true", help="只重建已有三次运行的比较报告，不重新运行实验。")
    parser.add_argument("--report-json", required=True)
    parser.add_argument("--summary-markdown", required=True)
    args = parser.parse_args(argv)
    if args.reuse_existing:
        report = analyze_existing_stability(
            worktree=Path(args.worktree),
            evidence_root=Path(args.evidence_root),
            manifest_path=Path(args.manifest) if args.manifest else None,
        )
        Path(args.evidence_root, "p2_stability_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    else:
        report = run_stability(
            worktree=Path(args.worktree),
            evidence_root=Path(args.evidence_root),
            python_executable=Path(args.python_executable),
            manifest_path=Path(args.manifest) if args.manifest else None,
            run_count=args.run_count,
            server_port=args.server_port,
            timeout_seconds=args.timeout_seconds,
        )
    try:
        if args.reuse_existing:
            Path(args.summary_markdown).parent.mkdir(parents=True, exist_ok=True)
            Path(args.summary_markdown).write_text(render_summary(report), encoding="utf-8")
            Path(args.report_json).parent.mkdir(parents=True, exist_ok=True)
            Path(args.report_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            write_summary(report, Path(args.summary_markdown))
            _write_new_file(Path(args.report_json), json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    except FileExistsError as exc:
        print(f"拒绝覆盖已有 P2 报告: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
