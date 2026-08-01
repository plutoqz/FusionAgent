from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_contract_case_experiments import run_manifest
from services.contract_experiment_service import load_experiment_manifest


VARIANTS = (
    ("full_method", "完整方法"),
    ("no_product_contract", "无产品契约"),
    ("no_quality_gate", "无质量门"),
    ("no_degraded_recovery", "无降级恢复"),
    ("fixed_priority", "固定优先级"),
)
VARIANT_NAMES = {name for name, _label in VARIANTS}
CASE_FILES = (
    "product_contract.json",
    "planning_decision.json",
    "resource_regime.json",
    "quality_gate_result.json",
    "gap_declaration.json",
    "evidence_trace.json",
    "delivery_manifest.json",
    "case_result.json",
)


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _stage_records(case_dir: Path, stage_ids: list[str]) -> list[dict[str, Any]]:
    records = []
    for stage_id in stage_ids:
        payload = load_json(case_dir / f"api_{stage_id}.json")
        if payload:
            records.append(payload)
    return records


def _summary(record: dict[str, Any]) -> dict[str, Any]:
    return load_json(Path(str(record.get("summary_path") or "")))


def _run_dir(experiment_dir: Path, child: dict[str, Any]) -> Path | None:
    run_id = str(child.get("run_id") or "").strip()
    if not run_id:
        return None
    path = experiment_dir / "runtime" / "runs" / run_id
    return path if path.exists() else None


def _quality_report(experiment_dir: Path, child: dict[str, Any]) -> dict[str, Any] | None:
    run_dir = _run_dir(experiment_dir, child)
    if run_dir is None:
        return None
    candidates = [run_dir / "output" / "quality_report.json", *run_dir.rglob("quality_report.json")]
    seen: set[Path] = set()
    for path in candidates:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        payload = load_json(path)
        if payload:
            return payload
    return None


def _validation_status(experiment_dir: Path, child: dict[str, Any]) -> bool | None:
    run_dir = _run_dir(experiment_dir, child)
    if run_dir is None:
        return None
    payload = load_json(run_dir / "validation.json")
    if not payload:
        return None
    return bool(payload.get("valid"))


def _child_ids(summary: dict[str, Any]) -> set[str]:
    return {
        str(child.get("run_id"))
        for child in summary.get("child_runs", [])
        if isinstance(child, dict) and child.get("run_id")
    }


def _first_quality_gate(summary: dict[str, Any], experiment_dir: Path) -> bool | None:
    children = [item for item in summary.get("child_runs", []) if isinstance(item, dict)]
    reports = [_quality_report(experiment_dir, child) for child in children]
    reports = [report for report in reports if report is not None]
    if not reports:
        return None
    if all(report.get("gate_status") == "disabled" for report in reports):
        return None
    if any(report.get("accepted") is False for report in reports):
        return False
    if any(str(child.get("phase")) == "failed" for child in children):
        return False
    return all(report.get("accepted") is True for report in reports)


def _initial_planning_valid(summary: dict[str, Any], experiment_dir: Path) -> bool | None:
    children = [item for item in summary.get("child_runs", []) if isinstance(item, dict)]
    values = [_validation_status(experiment_dir, child) for child in children]
    values = [value for value in values if value is not None]
    return all(values) if values else None


def _evidence_complete(case_dir: Path, summary: dict[str, Any], experiment_dir: Path) -> bool:
    if not all((case_dir / filename).exists() for filename in CASE_FILES):
        return False
    for child in summary.get("child_runs", []):
        if not isinstance(child, dict):
            continue
        run_dir = _run_dir(experiment_dir, child)
        if run_dir is None or not all((run_dir / filename).exists() for filename in ("plan.json", "validation.json", "audit.jsonl")):
            return False
    return True


def _runtime_contract_binding(summary: dict[str, Any], experiment_dir: Path) -> bool:
    for child in summary.get("child_runs", []):
        if not isinstance(child, dict):
            continue
        run_dir = _run_dir(experiment_dir, child)
        if run_dir is None:
            continue
        plan = load_json(run_dir / "plan.json")
        if plan.get("product_contract") is not None:
            return True
    return False


def _case_metrics(
    *,
    case: Any,
    case_dir: Path,
    experiment_dir: Path,
) -> dict[str, Any]:
    records = _stage_records(case_dir, [stage.stage_id for stage in case.stages])
    if not records:
        return {"case_id": case.case_id, "status": "missing_stage_records"}
    summaries = [_summary(record) for record in records]
    initial = summaries[0]
    final = summaries[-1]
    initial_record = records[0]
    final_record = records[-1]
    initial_ids = _child_ids(initial)
    final_ids = _child_ids(final)
    expected_final_phases = set(case.stages[-1].expected_phases)
    final_artifacts = [
        child
        for child in final.get("child_runs", [])
        if isinstance(child, dict) and child.get("artifact_path")
    ]
    key_layer = case.expected_layer_priority[0] if case.expected_layer_priority else None
    first_child = (initial.get("child_runs") or [{}])[0]
    task_order = list((initial.get("mission") or {}).get("task_kinds") or [])
    gaps = load_json(case_dir / "gap_declaration.json")
    observed_gap_types = {
        str(item.get("gap_type"))
        for item in gaps.get("observed_gaps", [])
        if isinstance(item, dict) and item.get("gap_type")
    }
    expected_gap_types = set(case.expected_gap_types)
    skipped_final_stage = bool(final_record.get("variant_stage_skipped"))
    recovery_case = len(case.stages) > 1
    recovery_child_count = len(final_ids - initial_ids)
    recovery_attempted = recovery_child_count > 0
    first_quality_gate_passed = _first_quality_gate(initial, experiment_dir)
    final_delivery_success = (
        not skipped_final_stage
        and final.get("phase") in expected_final_phases
        and bool(final_artifacts)
    )
    key_layer_on_time = bool(
        initial.get("phase") in {"succeeded", "partial", "partial_provisional"}
        and task_order
        and task_order[0] == key_layer
        and any(child.get("task_kind") == key_layer and child.get("artifact_path") for child in initial.get("child_runs", []))
    )
    recovery_success = None
    if recovery_case:
        recovery_success = bool(recovery_attempted and final_delivery_success)
    return {
        "case_id": case.case_id,
        "initial_phase": initial.get("phase"),
        "final_phase": final.get("phase"),
        "task_order": task_order,
        "planning_valid": _initial_planning_valid(initial, experiment_dir),
        "first_quality_gate_passed": first_quality_gate_passed,
        "final_delivery_success": final_delivery_success,
        "recovery_case": recovery_case,
        "recovery_attempted": recovery_attempted,
        "recovery_success": recovery_success,
        "recovery_cost_child_retries": recovery_child_count,
        "key_layer_delivered_on_time": key_layer_on_time,
        "gap_declaration_correct": expected_gap_types.issubset(observed_gap_types),
        "expected_gap_types": sorted(expected_gap_types),
        "observed_gap_types": sorted(observed_gap_types),
        "evidence_complete": _evidence_complete(case_dir, final, experiment_dir),
        "runtime_product_contract_bound": _runtime_contract_binding(initial, experiment_dir),
        "supersession_observed": bool(final.get("superseded_outputs")),
        "initial_child_count": len(initial.get("child_runs", [])),
        "final_child_count": len(final.get("child_runs", [])),
        "first_child_task": first_child.get("task_kind"),
    }


def _rate(values: list[bool | None]) -> float | None:
    observed = [value for value in values if value is not None]
    return sum(1 for value in observed if value) / len(observed) if observed else None


def _mean(values: list[int | float]) -> float | None:
    return sum(values) / len(values) if values else None


def _aggregate(case_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    recovery_metrics = [item for item in case_metrics if item.get("recovery_case")]
    return {
        "case_count": len(case_metrics),
        "planning_valid_rate": _rate([item.get("planning_valid") for item in case_metrics]),
        "first_quality_gate_pass_rate": _rate([item.get("first_quality_gate_passed") for item in case_metrics]),
        "final_delivery_success_rate": _rate([item.get("final_delivery_success") for item in case_metrics]),
        "recovery_success_rate": _rate([item.get("recovery_success") for item in recovery_metrics]),
        "recovery_cost_mean_child_retries": _mean([item.get("recovery_cost_child_retries", 0) for item in recovery_metrics]),
        "key_layer_on_time_rate": _rate([item.get("key_layer_delivered_on_time") for item in case_metrics]),
        "gap_declaration_correctness_rate": _rate([item.get("gap_declaration_correct") for item in case_metrics]),
        "evidence_completeness_rate": _rate([item.get("evidence_complete") for item in case_metrics]),
        "runtime_product_contract_binding_rate": _rate([item.get("runtime_product_contract_bound") for item in case_metrics]),
        "supersession_rate": _rate([item.get("supersession_observed") for item in case_metrics]),
        "quality_gate_bypassed_rate": _rate([item.get("first_quality_gate_passed") is None for item in case_metrics]),
    }


def _deltas(metrics: dict[str, Any], baseline: dict[str, Any]) -> dict[str, float | None]:
    result: dict[str, float | None] = {}
    for key, value in metrics.items():
        baseline_value = baseline.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool) and isinstance(baseline_value, (int, float)):
            result[key] = float(value) - float(baseline_value)
    return result


def _run_variant(*, variant: str, label: str, manifest_path: Path, experiment_dir: Path, port: int) -> dict[str, Any]:
    os.environ["GEOFUSION_P3_VARIANT"] = variant
    try:
        result = run_manifest(
            manifest_path=manifest_path,
            experiment_dir=experiment_dir,
            api_base_url=f"http://127.0.0.1:{port}",
            start_server=True,
            server_port=port,
            poll_seconds=2.0,
            timeout_seconds=1800.0,
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "variant": variant,
            "label": label,
            "status": "runner_error",
            "error": f"{type(exc).__name__}: {exc}",
            "experiment_dir": str(experiment_dir.resolve()),
        }

    manifest = load_experiment_manifest(manifest_path)
    case_metrics = [
        _case_metrics(
            case=case,
            case_dir=experiment_dir / "cases" / case.case_id,
            experiment_dir=experiment_dir,
        )
        for case in manifest.cases
    ]
    return {
        "variant": variant,
        "label": label,
        "status": "completed",
        "experiment_dir": str(experiment_dir.resolve()),
        "runtime_result": {
            "all_cases_passed": result.get("all_cases_passed"),
            "evidence_manifest_path": result.get("evidence_manifest_path"),
        },
        "case_metrics": case_metrics,
        "metrics": _aggregate(case_metrics),
    }


def build_report(*, manifest_path: Path, evidence_root: Path, server_port: int) -> dict[str, Any]:
    variants: list[dict[str, Any]] = []
    for index, (variant, label) in enumerate(VARIANTS):
        variants.append(
            _run_variant(
                variant=variant,
                label=label,
                manifest_path=manifest_path,
                experiment_dir=evidence_root / variant,
                port=server_port + index,
            )
        )
    baseline = next((item.get("metrics", {}) for item in variants if item.get("variant") == "full_method"), {})
    for item in variants:
        item["deltas_vs_full_method"] = _deltas(item.get("metrics", {}), baseline)
    return {
        "schema_version": "1.0.0",
        "p3_id": "freeze-c-governance-ablation-v1",
        "manifest_path": str(manifest_path.resolve()),
        "evidence_root": str(evidence_root.resolve()),
        "variants": [name for name, _label in VARIANTS],
        "fixed_environment": {
            "kg_backend": "memory",
            "llm_provider": "mock",
            "celery_eager": True,
            "scenario_child_max_workers": 1,
            "local_only": True,
            "artifact_reuse_disabled": True,
            "plan_grounding_mode": "report",
            "one_run_per_variant": True,
        },
        "variant_definitions": [
            {"variant": name, "label": label}
            for name, label in VARIANTS
        ],
        "results": variants,
        "limitations": [
            "每个变体只运行一次，当前结果用于最小治理方向筛查，不用于统计显著性结论。",
            "实验使用 memory KG、mock LLM、eager 执行和单 child worker。",
            "固定优先级变体只改变任务编译顺序；完整方法使用请求中的上下文任务顺序。",
            "P3 不比较融合算法本身，质量差异只用于观察质量门与恢复治理行为。",
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Freeze C P3 治理对照与消融摘要",
        "",
        "本轮为最小治理方向实验，每个变体在同一 C02/C04/C06 输入和固定环境下运行一次。结果用于筛查治理机制的行为差异，不构成统计显著性结论。",
        "",
        "| 变体 | 计划有效率 | 首次质量门通过率 | 最终交付成功率 | 恢复成功率 | 恢复代价 | 关键图层按时交付率 | gap 正确率 | 证据完整率 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in report["results"]:
        metrics = item.get("metrics", {})
        lines.append(
            "| {label} | {planning_valid_rate} | {first_quality_gate_pass_rate} | "
            "{final_delivery_success_rate} | {recovery_success_rate} | {recovery_cost_mean_child_retries} | "
            "{key_layer_on_time_rate} | {gap_declaration_correctness_rate} | {evidence_completeness_rate} |".format(
                label=item.get("label"),
                **metrics,
            )
        )
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "- `no_quality_gate` 的首次质量门通过率为不可用值时，表示质量门被绕过，不应解释为通过。",
            "- `no_degraded_recovery` 的恢复成功率以 C04/C06 的恢复机会为分母；跳过 resume 阶段计为恢复失败。",
            "- 结果中的 `deltas_vs_full_method` 由机器报告计算，论文引用前应结合每个案例的原始摘要和运行目录复核。",
            "",
            "原始运行目录、每个变体的 `experiment_evidence_manifest.json` 和逐案例证据均保留在机器报告的 `evidence_root` 下。",
        ]
    )
    return "\n".join(lines) + "\n"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the minimal Freeze C governance ablation matrix.")
    parser.add_argument(
        "--manifest",
        default=str(REPO_ROOT / "docs" / "thesis" / "manifests" / "2026-07-20-c02-c04-c06-real-data.json"),
    )
    parser.add_argument(
        "--evidence-root",
        default=r"D:\code\freeze-c-evidence\p3-governance-20260801-c02-c04-c06",
    )
    parser.add_argument("--report-json", default=str(REPO_ROOT / "docs" / "current" / "evidence" / "p3-governance" / "2026-08-01-freeze-c-p3-governance.json"))
    parser.add_argument("--summary-markdown", default=str(REPO_ROOT / "docs" / "current" / "evidence" / "p3-governance" / "2026-08-01-freeze-c-p3-governance.md"))
    parser.add_argument("--server-port", type=int, default=8230)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest_path = Path(args.manifest).resolve()
    evidence_root = Path(args.evidence_root).resolve()
    report = build_report(
        manifest_path=manifest_path,
        evidence_root=evidence_root,
        server_port=args.server_port,
    )
    report_json = Path(args.report_json).resolve()
    summary_markdown = Path(args.summary_markdown).resolve()
    report_json.parent.mkdir(parents=True, exist_ok=True)
    summary_markdown.parent.mkdir(parents=True, exist_ok=True)
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_markdown.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item.get("status") == "completed" for item in report["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
