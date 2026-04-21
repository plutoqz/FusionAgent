# Phase G Evidence Freeze Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Freeze a paper-grade evidence package that maps allowed FusionAgent claims to tracked benchmark summaries, explicit baseline rows, qualitative extension evidence, and reproducible curation commands.

**Architecture:** Keep Phase G focused on evidence tooling and documentation, not new runtime features. Extend the eval harness summary contract just enough to preserve matrix-ready evidence fields, add a standalone freeze script that renders JSON/Markdown from a tracked matrix spec, and record raw run artifact locations without committing `runs/` contents. The freeze tooling must accept both current `eval_harness` summary JSON and older single-case durable result JSON already tracked under `docs/superpowers/specs/`.

**Tech Stack:** Python 3.9+, pytest, existing `scripts/eval_harness.py`, JSON and Markdown evidence specs, existing v2 run/artifact conventions.

**Completion Status:** Implemented on 2026-04-21 in branch `codex/phase-g-experiment-matrix`. Focused verification passed with `21 passed`. Full repository verification passed with `180 passed, 1 skipped, 6 warnings`.

---

## File Structure

- Modify `scripts/eval_harness.py` to preserve manifest case metadata and emit matrix-ready evidence fields.
- Modify `tests/test_eval_harness.py` to lock the new harness summary contract.
- Create `scripts/freeze_paper_evidence.py` to normalize tracked benchmark summaries into frozen JSON and Markdown.
- Create `tests/test_freeze_paper_evidence.py` to lock path normalization, missing-case rejection, and failure-row rendering.
- Create `docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json` as the Phase G claim/baseline/case source of truth.
- Create `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json` as the generated machine-readable freeze.
- Create `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md` as the generated paper-facing report.
- Modify `docs/superpowers/specs/2026-04-20-evidence-ledger.md` to index Phase G evidence artifacts.
- Modify `docs/v2-operations.md` to document the freeze command and raw-artifact storage rule.

## Non-Goals

- Do not implement new ablation switches such as `kg_top_pattern_only` or `no_repair_or_replan`.
- Do not add new scenario-driven runtime behavior or another data/task vertical slice.
- Do not commit raw `runs/<run_id>/` directories, source caches, or large artifact bundles.
- Do not claim task-driven auto water acquisition; Phase F water evidence remains uploaded-only.
- Do not rewrite older tracked evidence files into one schema just to satisfy the freeze script; normalize them at read time instead.

### Task 1: Emit Matrix-Ready Harness Evidence

**Files:**
- Modify: `tests/test_eval_harness.py`
- Modify: `scripts/eval_harness.py`

- [x] **Step 1: Write the failing harness test**

Append to `tests/test_eval_harness.py`:

```python
def test_evaluate_manifest_cases_preserves_matrix_ready_case_metadata(monkeypatch) -> None:
    monkeypatch.setattr(eval_harness, "_preflight_manifest_api", lambda _base_url: None)
    monkeypatch.setattr(eval_harness, "_preflight_manifest_case_inputs", lambda _case: None)

    def fake_eval(*, case: dict, base_url: str, timeout_sec: float, runner, validator) -> dict:
        _ = runner
        _ = validator
        assert base_url == "http://unit.test"
        assert timeout_sec == 12.0
        return {
            "case_id": case["case_id"],
            "case_dir": None,
            "status": "passed",
            "duration_ms": 4,
            "run_id": "run-building-alpha",
            "artifact_size": 11,
            "artifact_entries": [
                "artifact/fused.shp",
                "artifact/fused.shx",
                "artifact/fused.dbf",
            ],
            "plan_algorithms": [
                "algo.fusion.building.v1",
                "algo.fusion.building.safe",
            ],
            "output_data_types": ["dt.building.fused"],
            "inspection_artifact_available": True,
            "inspection_download_path": "/api/v2/runs/run-building-alpha/artifact",
            "error": None,
            "timeout_sec": timeout_sec,
        }

    monkeypatch.setattr(eval_harness, "_evaluate_single_manifest_case", fake_eval)
    summary = eval_harness.evaluate_manifest_cases(
        cases=[
            {
                "case_id": "building_alpha",
                "theme": "building",
                "execution_mode": "agent",
                "readiness": "agent-ready",
                "priority": "P0",
                "baseline": "full_system",
                "proof_targets": ["C1", "C2"],
                "inputs": {
                    "osm_source_id": "raw.osm.building",
                    "reference_source_id": "raw.microsoft.building",
                },
                "notes": ["fresh checkout"],
                "expected_plan_checks": {
                    "required_algorithms": [
                        "algo.fusion.building.v1",
                        "algo.fusion.building.safe",
                    ],
                    "required_output_type": "dt.building.fused",
                },
                "artifact_checks": {"required_suffixes": [".shp", ".shx", ".dbf"]},
            }
        ],
        base_url="http://unit.test",
        timeout_sec=12.0,
    )

    case = summary["cases"][0]
    assert case["theme"] == "building"
    assert case["priority"] == "P0"
    assert case["baseline"] == "full_system"
    assert case["proof_targets"] == ["C1", "C2"]
    assert case["inputs"]["osm_source_id"] == "raw.osm.building"
    assert case["evidence"]["planning_validity"] is True
    assert case["evidence"]["artifact_validity"] is True
    assert case["evidence"]["observed_algorithms"] == [
        "algo.fusion.building.v1",
        "algo.fusion.building.safe",
    ]
    assert case["evidence"]["observed_output_types"] == ["dt.building.fused"]
```

- [x] **Step 2: Run the test and verify it fails**

Run:

```powershell
python -m pytest -q tests/test_eval_harness.py -k matrix_ready_case_metadata
```

Expected: FAIL because `evaluate_manifest_cases()` does not preserve `baseline`, `proof_targets`, or nested `evidence`.

- [x] **Step 3: Implement manifest metadata and evidence emission**

In `scripts/eval_harness.py`, add helpers:

```python
def _ordered_strings(values: Any) -> list[str]:
    ordered: list[str] = []
    if not isinstance(values, list):
        return ordered
    for value in values:
        text = str(value or "").strip()
        if text and text not in ordered:
            ordered.append(text)
    return ordered


def _collect_plan_algorithms(plan: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    for task in plan.get("tasks", []):
        if not isinstance(task, dict):
            continue
        candidates = [task.get("algorithm_id"), *(task.get("alternatives") or [])]
        for candidate in candidates:
            text = str(candidate or "").strip()
            if text and text not in ordered:
                ordered.append(text)
    retrieval = plan.get("context", {}).get("retrieval", {}).get("algorithms", {})
    if isinstance(retrieval, dict):
        for algorithm_id in retrieval.keys():
            text = str(algorithm_id or "").strip()
            if text and text not in ordered:
                ordered.append(text)
    return ordered


def _collect_output_data_types(plan: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    for task in plan.get("tasks", []):
        if not isinstance(task, dict):
            continue
        text = str(task.get("output", {}).get("data_type_id") or "").strip()
        if text and text not in ordered:
            ordered.append(text)
    return ordered
```

Also add:

```python
def _build_manifest_case_metadata(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "theme": str(case.get("theme") or ""),
        "priority": str(case.get("priority") or ""),
        "baseline": str(case.get("baseline") or "full_system"),
        "proof_targets": _ordered_strings(case.get("proof_targets") or []),
        "inputs": dict(case.get("inputs") or {}),
        "notes": _ordered_strings(case.get("notes") or []),
        "clip_bbox": case.get("clip_bbox"),
    }


def _build_manifest_case_evidence(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    expected_plan_checks = case.get("expected_plan_checks") or {}
    artifact_checks = case.get("artifact_checks") or {}
    artifact_entries = _ordered_strings(result.get("artifact_entries") or [])
    required_suffixes = _ordered_strings(artifact_checks.get("required_suffixes") or [])
    artifact_validity = bool(
        result.get("status") == "passed"
        and required_suffixes
        and all(any(entry.endswith(suffix) for entry in artifact_entries) for suffix in required_suffixes)
    )
    if not required_suffixes and result.get("status") == "passed":
        artifact_validity = bool(artifact_entries or result.get("artifact_size"))
    return {
        "planning_validity": result.get("status") == "passed",
        "artifact_validity": artifact_validity,
        "inspection_artifact_available": bool(result.get("inspection_artifact_available")),
        "inspection_download_path": result.get("inspection_download_path"),
        "required_algorithms": _ordered_strings(expected_plan_checks.get("required_algorithms") or []),
        "observed_algorithms": _ordered_strings(result.get("plan_algorithms") or []),
        "required_output_type": str(expected_plan_checks.get("required_output_type") or ""),
        "observed_output_types": _ordered_strings(result.get("output_data_types") or []),
        "required_suffixes": required_suffixes,
        "artifact_entries": artifact_entries,
    }
```

Update `_evaluate_single_manifest_case()` so it returns these fields from the existing runner result:

```python
artifact_entries = _ordered_strings(result.get("artifact_entries") or [])
plan = result.get("plan") or {}
plan_algorithms = _collect_plan_algorithms(plan)
output_data_types = _collect_output_data_types(plan)
inspection_artifact_available = bool(artifact_entries)
inspection_download_path = f"/api/v2/runs/{run_id}/artifact" if run_id and artifact_entries else None
```

Then update the runnable branch in `evaluate_manifest_cases()`:

```python
case_result = _evaluate_single_manifest_case(
    case=case,
    base_url=base_url,
    timeout_sec=effective_timeout_sec,
    runner=runner,
    validator=validator,
)
case_result.update(_build_manifest_case_metadata(case))
case_result["evidence"] = _build_manifest_case_evidence(case, case_result)
results.append(case_result)
```

- [x] **Step 4: Run the harness test and verify it passes**

Run:

```powershell
python -m pytest -q tests/test_eval_harness.py -k matrix_ready_case_metadata
```

Expected: PASS.

- [x] **Step 5: Commit the harness slice**

Run:

```powershell
git add scripts/eval_harness.py tests/test_eval_harness.py
git commit -m "feat: capture matrix-ready eval evidence"
```

### Task 2: Add Paper Evidence Freeze Tooling

**Files:**
- Create: `tests/test_freeze_paper_evidence.py`
- Create: `scripts/freeze_paper_evidence.py`

- [x] **Step 1: Write the failing freeze-script tests**

Create `tests/test_freeze_paper_evidence.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import freeze_paper_evidence


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_freeze_report_normalizes_paths_and_renders_failure_rows(tmp_path: Path) -> None:
    summary_path = tmp_path / "docs" / "superpowers" / "specs" / "building-real.json"
    old_manifest = (
        "C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/old/"
        "docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json"
    )
    _write_json(
        summary_path,
        {
            "generated_at": "2026-04-21T00:00:00Z",
            "base_url": "http://127.0.0.1:8010",
            "timeout_sec": 1200.0,
            "commit_sha": "abc123",
            "manifest": old_manifest,
            "environment": {
                "kg_backend": "neo4j",
                "llm_provider": "openai",
                "celery_eager": "0",
            },
            "cases": [
                {
                    "case_id": "building_real",
                    "status": "passed",
                    "run_id": "run-building-real",
                    "timeout_sec": 1200.0,
                    "evidence": {
                        "planning_validity": True,
                        "artifact_validity": True,
                        "inspection_artifact_available": True,
                        "inspection_download_path": "/api/v2/runs/run-building-real/artifact",
                    },
                }
            ],
        },
    )
    manifest_path = tmp_path / "docs" / "superpowers" / "specs" / "2026-04-07-real-data-eval-manifest.json"
    _write_json(manifest_path, {"version": "test"})

    spec_path = tmp_path / "docs" / "superpowers" / "specs" / "matrix.json"
    _write_json(
        spec_path,
        {
            "version": "2026-04-21",
            "rows": [
                {
                    "row_id": "c1_building_real",
                    "claim_ids": ["C1", "C2"],
                    "baseline": "full_system",
                    "dataset": "Gitega OSM vs Google buildings",
                    "case_id": "building_real",
                    "summary_json": "docs/superpowers/specs/building-real.json",
                    "command": ["python", "scripts/eval_harness.py", "--case", "building_real"],
                    "artifact_storage": "runs/run-building-real",
                    "supports_metrics": ["execution_success_rate", "artifact_validity"],
                },
                {
                    "row_id": "failure_alignment_drift",
                    "claim_ids": ["C2-boundary"],
                    "baseline": "historical_failure",
                    "dataset": "Historical micro alignment drift",
                    "case_id": "building_real",
                    "summary_json": "docs/superpowers/specs/building-real.json",
                    "command": ["historical", "reference"],
                    "artifact_storage": "api-only run",
                    "supports_metrics": ["execution_success_rate"],
                    "expected_status": "failed",
                    "analysis": "Historical runtime alignment drift should stay visible.",
                },
            ],
            "qualitative_evidence": [
                {
                    "evidence_id": "c7_water_uploaded_vertical_slice",
                    "claim_ids": ["C7"],
                    "paths": ["docs/superpowers/plans/2026-04-20-water-vertical-slice.md"],
                    "summary": "Uploaded-only water slice proves bounded extensibility.",
                }
            ],
        },
    )

    report = freeze_paper_evidence.build_freeze_report(repo_root=tmp_path, spec_path=spec_path)
    markdown = freeze_paper_evidence.render_markdown(report)

    assert report["rows"][0]["manifest"] == "docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json"
    assert report["rows"][0]["raw_artifacts"]["run_json"] == "runs/run-building-real/run.json"
    assert report["rows"][0]["metrics"]["artifact_validity"] == "pass"
    assert report["failure_rows"][0]["row_id"] == "failure_alignment_drift"
    assert report["qualitative_evidence"][0]["evidence_id"] == "c7_water_uploaded_vertical_slice"
    assert "Historical runtime alignment drift" in markdown


def test_build_freeze_report_rejects_missing_case_id(tmp_path: Path) -> None:
    summary_path = tmp_path / "docs" / "superpowers" / "specs" / "building-real.json"
    _write_json(summary_path, {"generated_at": "2026-04-21T00:00:00Z", "cases": []})
    spec_path = tmp_path / "docs" / "superpowers" / "specs" / "matrix.json"
    _write_json(
        spec_path,
        {
            "version": "2026-04-21",
            "rows": [
                {
                    "row_id": "missing_case_row",
                    "claim_ids": ["C1"],
                    "baseline": "full_system",
                    "dataset": "broken",
                    "case_id": "missing_case",
                    "summary_json": "docs/superpowers/specs/building-real.json",
                    "command": ["python", "scripts/eval_harness.py"],
                    "artifact_storage": "runs/missing-case",
                    "supports_metrics": ["execution_success_rate"],
                }
            ],
        },
    )

    with pytest.raises(ValueError, match="Case 'missing_case' not found"):
        freeze_paper_evidence.build_freeze_report(repo_root=tmp_path, spec_path=spec_path)
```

- [x] **Step 2: Run the tests and verify they fail**

Run:

```powershell
python -m pytest -q tests/test_freeze_paper_evidence.py
```

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.freeze_paper_evidence'`.

- [x] **Step 3: Implement the freeze script**

Create `scripts/freeze_paper_evidence.py` with these exported functions and CLI:

```python
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _coerce_repo_relative(value: str | None, *, repo_root: Path) -> str | None:
    if not value:
        return None
    raw = Path(value)
    if raw.is_absolute():
        try:
            return raw.resolve().relative_to(repo_root.resolve()).as_posix()
        except Exception:
            parts = raw.parts
            for index in range(len(parts)):
                candidate = repo_root / Path(*parts[index:])
                if candidate.exists():
                    return candidate.relative_to(repo_root).as_posix()
    candidate = repo_root / value
    if candidate.exists():
        return candidate.relative_to(repo_root).as_posix()
    return value.replace("\\", "/")


def _metric_value(name: str, *, case: dict[str, Any], row: dict[str, Any]) -> str:
    evidence = case.get("evidence") or {}
    if name == "execution_success_rate":
        return "pass" if case.get("status") == "passed" else "fail"
    if name == "planning_validity_rate":
        return "pass" if evidence.get("planning_validity") else "fail"
    if name == "artifact_validity":
        return "pass" if evidence.get("artifact_validity") else "fail"
    if name == "evidence_completeness_rate":
        return "pass" if case.get("run_id") and row.get("artifact_storage") else "fail"
    if name == "reproducibility_status":
        return str(row.get("reproducibility") or "unknown")
    return "n/a"


def build_freeze_report(*, repo_root: Path, spec_path: Path) -> dict[str, Any]:
    spec = _load_json(spec_path)
    rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    for row in spec.get("rows", []):
        summary_rel = _coerce_repo_relative(str(row["summary_json"]), repo_root=repo_root)
        summary = _load_json(repo_root / summary_rel)
        case_id = str(row["case_id"])
        case = next((item for item in summary.get("cases", []) if item.get("case_id") == case_id), None)
        if case is None:
            raise ValueError(f"Case '{case_id}' not found in {summary_rel}")
        run_id = case.get("run_id")
        frozen_row = {
            "row_id": row["row_id"],
            "claim_ids": list(row.get("claim_ids") or []),
            "baseline": row["baseline"],
            "dataset": row["dataset"],
            "case_id": case_id,
            "expected_status": row.get("expected_status") or "passed",
            "observed_status": case.get("status"),
            "summary_json": summary_rel,
            "manifest": _coerce_repo_relative(summary.get("manifest"), repo_root=repo_root),
            "command": row["command"],
            "commit_sha": summary.get("commit_sha"),
            "base_url": summary.get("base_url"),
            "timeout_sec": case.get("timeout_sec", summary.get("timeout_sec")),
            "environment": dict(summary.get("environment") or {}),
            "run_id": run_id,
            "artifact_storage": row.get("artifact_storage"),
            "raw_artifacts": {
                "run_json": f"runs/{run_id}/run.json" if run_id else None,
                "plan_json": f"runs/{run_id}/plan.json" if run_id else None,
                "validation_json": f"runs/{run_id}/validation.json" if run_id else None,
                "audit_jsonl": f"runs/{run_id}/audit.jsonl" if run_id else None,
                "artifact_bundle": row.get("artifact_storage"),
            },
            "metrics": {
                metric: _metric_value(metric, case=case, row=row)
                for metric in row.get("supports_metrics", [])
            },
            "evidence": dict(case.get("evidence") or {}),
            "analysis": row.get("analysis"),
        }
        rows.append(frozen_row)
        if frozen_row["expected_status"] != "passed" or frozen_row["observed_status"] != "passed":
            failure_rows.append(frozen_row)
    return {
        "version": spec.get("version"),
        "spec_path": _coerce_repo_relative(str(spec_path), repo_root=repo_root),
        "rows": rows,
        "failure_rows": failure_rows,
        "qualitative_evidence": list(spec.get("qualitative_evidence") or []),
    }
```

Also add Markdown rendering and CLI:

```python
def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Paper Evidence Freeze",
        "",
        "| Row | Claims | Baseline | Dataset | Observed Status | Summary |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in report["rows"]:
        lines.append(
            f"| {row['row_id']} | {', '.join(row['claim_ids'])} | {row['baseline']} | "
            f"{row['dataset']} | {row['observed_status']} | `{row['summary_json']}` |"
        )
    lines.extend(["", "## Failure Analysis", ""])
    if report["failure_rows"]:
        for row in report["failure_rows"]:
            lines.append(f"- `{row['row_id']}`: {row.get('analysis') or 'No analysis recorded.'}")
    else:
        lines.append("- No frozen failure rows.")
    lines.extend(["", "## Qualitative Evidence", ""])
    for item in report["qualitative_evidence"]:
        claims = ", ".join(item.get("claim_ids", []))
        lines.append(f"- `{item['evidence_id']}` ({claims}): {item['summary']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Freeze paper evidence from tracked experiment summaries.")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-markdown", required=True)
    args = parser.parse_args(argv)

    repo_root = Path(__file__).resolve().parents[1]
    report = build_freeze_report(repo_root=repo_root, spec_path=Path(args.spec).resolve())
    output_json = Path(args.output_json).resolve()
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_markdown = Path(args.output_markdown).resolve()
    output_markdown.parent.mkdir(parents=True, exist_ok=True)
    output_markdown.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [x] **Step 4: Run the freeze-script tests and verify they pass**

Run:

```powershell
python -m pytest -q tests/test_freeze_paper_evidence.py
```

Expected: PASS.

- [x] **Step 5: Commit the freeze-tooling slice**

Run:

```powershell
git add scripts/freeze_paper_evidence.py tests/test_freeze_paper_evidence.py
git commit -m "feat: add paper evidence freeze tooling"
```

### Task 3: Author The Phase G Matrix Spec And Generate Frozen Outputs

**Files:**
- Create: `docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json`
- Create: `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json`
- Create: `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md`

- [x] **Step 1: Write the experiment matrix spec**

Create `docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json`:

```json
{
  "version": "2026-04-21",
  "rows": [
    {
      "row_id": "c1_c2_building_google_full_system",
      "claim_ids": ["C1", "C2"],
      "baseline": "full_system",
      "dataset": "Gitega building OSM vs Google",
      "case_id": "building_gitega_osm_vs_google_agent",
      "summary_json": "docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json",
      "command": [
        "python",
        "scripts/eval_harness.py",
        "--manifest",
        "docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json",
        "--case",
        "building_gitega_osm_vs_google_agent",
        "--base-url",
        "http://127.0.0.1:8011",
        "--timeout",
        "1200",
        "--output-json",
        "tmp/eval/building-real.json"
      ],
      "artifact_storage": "runs/0b4315edf3a8449d940355717ad70fa7",
      "supports_metrics": [
        "planning_validity_rate",
        "execution_success_rate",
        "artifact_validity",
        "evidence_completeness_rate"
      ]
    },
    {
      "row_id": "c5_building_msft_manual_baseline_contrast",
      "claim_ids": ["C5"],
      "baseline": "manual_input_baseline",
      "dataset": "Gitega micro building OSM vs Microsoft, source-id materialized",
      "case_id": "building_gitega_micro_msft_agent",
      "summary_json": "docs/superpowers/specs/2026-04-16-building-micro-msft-fresh-checkout-result.json",
      "command": [
        "python",
        "scripts/eval_harness.py",
        "--manifest",
        "docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json",
        "--case",
        "building_gitega_micro_msft_agent",
        "--base-url",
        "http://127.0.0.1:8010",
        "--timeout",
        "1200",
        "--output-json",
        "tmp/eval/fresh-checkout-micro-msft.json"
      ],
      "artifact_storage": "runs/60e7afca80e146cd819fe87966d47e8c",
      "reproducibility": "tracked_source_ids",
      "supports_metrics": [
        "execution_success_rate",
        "artifact_validity",
        "evidence_completeness_rate",
        "reproducibility_status"
      ]
    },
    {
      "row_id": "failure_micro_alignment_drift",
      "claim_ids": ["C2-boundary"],
      "baseline": "historical_failure",
      "dataset": "Gitega micro building OSM vs Google",
      "case_id": "building_gitega_micro_agent",
      "summary_json": "docs/superpowers/specs/2026-04-08-building-micro-benchmark-result.json",
      "command": [
        "python",
        "scripts/eval_harness.py",
        "--manifest",
        "docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json",
        "--case",
        "building_gitega_micro_agent",
        "--base-url",
        "http://127.0.0.1:8012",
        "--timeout",
        "1200",
        "--output-json",
        "tmp/eval/building-micro.json"
      ],
      "artifact_storage": "api-only run 8319c5bba5f64dd1a88ace78debaace5",
      "supports_metrics": ["execution_success_rate"],
      "expected_status": "failed",
      "analysis": "Historical worker/runtime alignment drift, superseded by the clean 2026-04-16 rerun."
    }
  ],
  "qualitative_evidence": [
    {
      "evidence_id": "c7_water_uploaded_vertical_slice",
      "claim_ids": ["C7"],
      "paths": [
        "docs/superpowers/plans/2026-04-20-water-vertical-slice.md",
        "tests/test_water_adapter.py",
        "tests/test_api_v2_integration.py::test_v2_run_water_uploaded_integration",
        "docs/superpowers/specs/2026-04-20-evidence-ledger.md"
      ],
      "summary": "Uploaded-only water slice proves bounded extensibility beyond building and road without claiming task-driven auto water acquisition."
    }
  ]
}
```

- [x] **Step 2: Generate the frozen evidence outputs**

Run:

```powershell
python scripts/freeze_paper_evidence.py `
  --spec docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json `
  --output-json docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json `
  --output-markdown docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md
```

Expected: both output files exist, summary and manifest paths are repo-relative, and the Markdown includes `Failure Analysis` plus `c7_water_uploaded_vertical_slice`.

- [x] **Step 3: Commit the matrix and freeze artifacts**

Run:

```powershell
git add docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json `
  docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json `
  docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md
git commit -m "docs: freeze phase g paper evidence"
```

### Task 4: Update Durable Evidence Docs

**Files:**
- Modify: `docs/superpowers/specs/2026-04-20-evidence-ledger.md`
- Modify: `docs/v2-operations.md`

- [x] **Step 1: Add Phase G entries to the evidence ledger**

Add rows in `docs/superpowers/specs/2026-04-20-evidence-ledger.md`:

```markdown
| Phase G experiment matrix spec | `docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json` | Frozen claim/baseline/case contract for paper evidence | strong | Source of truth for Phase G evidence curation |
| Phase G paper evidence freeze | `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json`, `docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md` | Paper-grade summary, failure analysis, and raw-artifact traceability notes | strong | Generated from tracked benchmark summaries plus qualitative Phase F references |
```

- [x] **Step 2: Document the freeze command and storage rule**

Add to `docs/v2-operations.md` after the Tier 3 benchmark guidance:

````markdown
### Phase G Evidence Freeze

After benchmark reruns are curated, freeze the tracked paper evidence with:

```powershell
python scripts/freeze_paper_evidence.py `
  --spec docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json `
  --output-json docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json `
  --output-markdown docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md
```

Track the spec and frozen outputs under `docs/superpowers/specs/`.
Do not track raw `runs/<run_id>/` directories or source caches; record their storage location inside the frozen JSON instead.
````

- [x] **Step 3: Verify and commit doc alignment**

Run:

```powershell
Select-String -Path docs/superpowers/specs/2026-04-20-evidence-ledger.md,docs/v2-operations.md `
  -Pattern 'Phase G|paper evidence freeze|freeze_paper_evidence.py'
git add docs/superpowers/specs/2026-04-20-evidence-ledger.md docs/v2-operations.md
git commit -m "docs: align phase g evidence references"
```

Expected: `Select-String` returns matches in both files, then the commit succeeds.

### Task 5: Verify The Whole Phase G Slice

**Files:**
- Modify/Create all files listed in the File Structure section.

- [x] **Step 1: Run focused verification**

Run:

```powershell
python -m pytest -q tests/test_eval_harness.py tests/test_freeze_paper_evidence.py
```

Expected: PASS.

- [x] **Step 2: Rebuild frozen artifacts**

Run:

```powershell
python scripts/freeze_paper_evidence.py `
  --spec docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json `
  --output-json docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json `
  --output-markdown docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md
```

Expected: command exits `0` and no unexpected diff appears outside the planned Phase G files.

- [x] **Step 3: Run full repository verification**

Run:

```powershell
python -m pytest -q
```

Expected:

```text
180 passed, 1 skipped, 6 warnings
```

The only warnings should remain the known `pyproj`/`numpy` deprecation noise from `tests/test_building_adapter_safe.py`.

- [x] **Step 4: Check diff and placeholder hygiene**

Run:

```powershell
git diff --check
Select-String -Path docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json, `
  docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json, `
  docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md `
  -Pattern 'TODO|TBD|placeholder'
```

Expected:

```text
git diff --check: no output
Select-String: no matches
```

- [x] **Step 5: Create the final implementation commit**

Run:

```powershell
git add scripts/eval_harness.py scripts/freeze_paper_evidence.py `
  tests/test_eval_harness.py tests/test_freeze_paper_evidence.py `
  docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json `
  docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json `
  docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md `
  docs/superpowers/specs/2026-04-20-evidence-ledger.md `
  docs/v2-operations.md
git commit -m "feat: freeze phase g paper evidence matrix"
```

## Gate After Phase G

Continue to Phase H only if:

- the frozen matrix covers every in-scope claim from `docs/superpowers/specs/2026-04-20-evaluation-contract-claim-lock.md`
- the failure section clearly documents what remains boundary-only or historical drift
- the qualitative Phase F water note is sufficient for the extensibility narrative without opening another runtime slice

If any required claim still lacks frozen evidence, return only to the weakest prior phase that can supply it. Do not open unrelated operator-surface work before the evidence freeze is stable.

## Self-Review

- Spec coverage: this plan covers harness evidence capture, frozen matrix generation, tracked spec/report outputs, evidence-ledger alignment, and end-to-end verification.
- Placeholder scan: all steps name exact files, commands, and expected outputs.
- Type consistency: claim ids use the `C1`/`C2`/`C5`/`C7` contract from the evaluation spec, while metrics use names from `2026-04-20-evaluation-contract-claim-lock.md`.

