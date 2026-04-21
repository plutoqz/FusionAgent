from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import freeze_paper_evidence


_REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_build_freeze_report_normalizes_harness_summary_and_renders_failure_rows(tmp_path: Path) -> None:
    summary_path = tmp_path / "docs" / "superpowers" / "specs" / "building-real.json"
    old_manifest = (
        "C:/Users/QDX/.config/superpowers/worktrees/fusionAgent/old/"
        "docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json"
    )
    _write_json(
        summary_path,
        {
            "generated_at": "2026-04-21T00:00:00Z",
            "command_mode": "manifest",
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


def test_build_freeze_report_supports_single_case_durable_result_json(tmp_path: Path) -> None:
    summary_path = tmp_path / "docs" / "superpowers" / "specs" / "micro-msft.json"
    _write_json(
        summary_path,
        {
            "case_id": "building_msft",
            "case_name": "Fresh-checkout reproducibility micro benchmark",
            "status": "passed",
            "run_id": "run-msft",
            "duration_ms": 207420,
            "artifact_size_bytes": 4399017,
            "runner": {
                "base_url": "http://127.0.0.1:8010",
                "timeout_seconds": 180,
            },
            "environment": {
                "kg_backend": "neo4j",
                "llm_provider": "openai",
                "celery_eager": 0,
            },
            "inputs": {
                "bbox": [29.817351, -3.646572, 29.931113, -3.412421],
                "source_ids": ["raw.osm.building", "raw.microsoft.building"],
            },
            "evidence_origin": {
                "output_json": "tmp/eval/fresh-checkout-micro-msft.json",
                "manifest": "docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json",
                "generated_at": "2026-04-16",
            },
            "notes": [
                "This evidence captures the bounded fresh-checkout reproducibility path.",
            ],
        },
    )

    spec_path = tmp_path / "docs" / "superpowers" / "specs" / "matrix.json"
    _write_json(
        spec_path,
        {
            "version": "2026-04-21",
            "rows": [
                {
                    "row_id": "c5_building_msft_manual_baseline_contrast",
                    "claim_ids": ["C5"],
                    "baseline": "manual_input_baseline",
                    "dataset": "Gitega micro building OSM vs Microsoft",
                    "case_id": "building_msft",
                    "summary_json": "docs/superpowers/specs/micro-msft.json",
                    "command": ["python", "scripts/eval_harness.py", "--case", "building_msft"],
                    "artifact_storage": "runs/run-msft",
                    "reproducibility": "tracked_source_ids",
                    "supports_metrics": [
                        "execution_success_rate",
                        "artifact_validity",
                        "evidence_completeness_rate",
                        "reproducibility_status",
                    ],
                }
            ],
        },
    )

    report = freeze_paper_evidence.build_freeze_report(repo_root=tmp_path, spec_path=spec_path)
    row = report["rows"][0]

    assert row["case_name"] == "Fresh-checkout reproducibility micro benchmark"
    assert row["manifest"] == "docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json"
    assert row["base_url"] == "http://127.0.0.1:8010"
    assert row["timeout_sec"] == 180
    assert row["metrics"]["artifact_validity"] == "pass"
    assert row["metrics"]["reproducibility_status"] == "tracked_source_ids"
    assert row["evidence"]["artifact_validity"] is True
    assert row["raw_artifacts"]["artifact_bundle"] == "runs/run-msft"


def test_build_freeze_report_derives_legacy_harness_evidence_when_missing(tmp_path: Path) -> None:
    summary_path = tmp_path / "docs" / "superpowers" / "specs" / "legacy-summary.json"
    _write_json(
        summary_path,
        {
            "generated_at": "2026-04-21T00:00:00Z",
            "base_url": "http://127.0.0.1:8011",
            "timeout_sec": 1200.0,
            "commit_sha": "abc123",
            "cases": [
                {
                    "case_id": "legacy_case",
                    "status": "passed",
                    "run_id": "run-legacy",
                    "artifact_size": 2048,
                    "timeout_sec": 1200.0,
                }
            ],
        },
    )
    spec_path = tmp_path / "docs" / "superpowers" / "specs" / "matrix.json"
    _write_json(
        spec_path,
        {
            "version": "2026-04-21",
            "rows": [
                {
                    "row_id": "legacy_row",
                    "claim_ids": ["C1"],
                    "baseline": "full_system",
                    "dataset": "legacy summary",
                    "case_id": "legacy_case",
                    "summary_json": "docs/superpowers/specs/legacy-summary.json",
                    "command": ["python", "scripts/eval_harness.py", "--case", "legacy_case"],
                    "artifact_storage": "runs/run-legacy",
                    "supports_metrics": [
                        "planning_validity_rate",
                        "execution_success_rate",
                        "artifact_validity",
                    ],
                }
            ],
        },
    )

    report = freeze_paper_evidence.build_freeze_report(repo_root=tmp_path, spec_path=spec_path)
    row = report["rows"][0]

    assert row["metrics"]["planning_validity_rate"] == "pass"
    assert row["metrics"]["artifact_validity"] == "pass"
    assert row["evidence"]["inspection_download_path"] == "/api/v2/runs/run-legacy/artifact"


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


def test_build_freeze_report_supports_status_evidence_rows_and_renders_metric_details(tmp_path: Path) -> None:
    spec_path = tmp_path / "docs" / "superpowers" / "specs" / "matrix.json"
    _write_json(
        spec_path,
        {
            "version": "2026-04-21",
            "rows": [
                {
                    "row_id": "c3_replan_fault_recovery",
                    "claim_ids": ["C3"],
                    "baseline": "no_repair_or_replan",
                    "dataset": "fault-injected task-driven water/building/road runtime",
                    "summary_kind": "verification",
                    "observed_status": "passed",
                    "summary": "Focused replan regression checks passed and preserved plan revisions.",
                    "verification_command": [
                        "python",
                        "-m",
                        "pytest",
                        "-q",
                        "tests/test_agent_run_service_enhancements.py::test_task_driven_replan_refreshes_inputs_when_source_changes",
                    ],
                    "verification_result": "2 passed",
                    "evidence_paths": [
                        "docs/superpowers/plans/2026-04-20-full-replan-loop-v1.md",
                        "tests/test_agent_run_service_enhancements.py",
                    ],
                    "supports_metrics": [
                        "recovery_success_rate",
                        "decision_trace_completeness",
                        "execution_success_rate",
                    ],
                },
                {
                    "row_id": "c1_c2_c7_scenario_trigger_autonomy",
                    "claim_ids": ["C1", "C2", "C7"],
                    "baseline": "full_system",
                    "dataset": "local file-inbox triggered disaster scenario",
                    "summary_kind": "scenario_trigger_proof",
                    "observed_status": "passed",
                    "summary": "Local trigger event normalizes into a scenario run and freezes reports.",
                    "verification_command": [
                        "python",
                        "-m",
                        "pytest",
                        "-q",
                        "tests/test_scenario_trigger_service.py",
                        "tests/test_scenario_registry_service.py",
                        "tests/test_api_scenario_registry.py",
                    ],
                    "verification_result": "13 passed",
                    "evidence_paths": [
                        "docs/superpowers/specs/2026-04-21-scenario-trigger-proof.md",
                        "docs/superpowers/specs/2026-04-21-scenario-evidence-freeze.md",
                    ],
                    "supports_metrics": [
                        "planning_validity_rate",
                        "evidence_completeness_rate",
                        "decision_trace_completeness",
                    ],
                },
            ],
            "qualitative_evidence": [
                {
                    "evidence_id": "c7_water_task_driven_auto_extensibility",
                    "claim_ids": ["C7"],
                    "paths": ["docs/superpowers/specs/2026-04-20-evidence-ledger.md"],
                    "summary": "Water shares the same task-driven runtime and evidence contract after Phase 1 stabilization.",
                }
            ],
        },
    )

    report = freeze_paper_evidence.build_freeze_report(repo_root=tmp_path, spec_path=spec_path)
    markdown = freeze_paper_evidence.render_markdown(report)
    row = report["rows"][0]
    scenario_row = report["rows"][1]

    assert row["summary_source_format"] == "verification"
    assert row["metrics"] == {
        "recovery_success_rate": "pass",
        "decision_trace_completeness": "pass",
        "execution_success_rate": "pass",
    }
    assert row["evidence_paths"] == [
        "docs/superpowers/plans/2026-04-20-full-replan-loop-v1.md",
        "tests/test_agent_run_service_enhancements.py",
    ]
    assert scenario_row["summary_source_format"] == "scenario_trigger_proof"
    assert scenario_row["observed_status"] == "passed"
    assert scenario_row["metrics"] == {
        "planning_validity_rate": "pass",
        "evidence_completeness_rate": "pass",
        "decision_trace_completeness": "pass",
    }
    assert scenario_row["verification_command"] == [
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/test_scenario_trigger_service.py",
        "tests/test_scenario_registry_service.py",
        "tests/test_api_scenario_registry.py",
    ]
    assert scenario_row["verification_result"] == "13 passed"
    assert report["failure_rows"] == []
    assert "recovery_success_rate=pass" in markdown
    assert "c1_c2_c7_scenario_trigger_autonomy" in markdown
    assert "planning_validity_rate=pass" in markdown
    assert "13 passed" in markdown
    assert "docs/superpowers/plans/2026-04-20-full-replan-loop-v1.md" in markdown
    assert "Water shares the same task-driven runtime and evidence contract after Phase 1 stabilization." in markdown


def test_repo_paper_experiment_matrix_and_freeze_outputs_promote_c3_c4_and_add_c7_c8_rows() -> None:
    matrix_path = _REPO_ROOT / "docs" / "superpowers" / "specs" / "2026-04-21-paper-experiment-matrix.json"
    freeze_json_path = _REPO_ROOT / "docs" / "superpowers" / "specs" / "2026-04-21-paper-evidence-freeze.json"
    freeze_md_path = _REPO_ROOT / "docs" / "superpowers" / "specs" / "2026-04-21-paper-evidence-freeze.md"

    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    rows_by_id = {row["row_id"]: row for row in matrix["rows"]}
    assert rows_by_id["c3_replan_fault_recovery"]["claim_ids"] == ["C3"]
    assert rows_by_id["c3_replan_fault_recovery"]["baseline"] == "no_repair_or_replan"
    assert rows_by_id["c3_replan_fault_recovery"]["supports_metrics"] == [
        "recovery_success_rate",
        "decision_trace_completeness",
        "execution_success_rate",
    ]
    assert rows_by_id["c4_learning_hints_pattern_selection"]["claim_ids"] == ["C4"]
    assert rows_by_id["c4_learning_hints_pattern_selection"]["baseline"] == "no_durable_learning_hints"
    assert rows_by_id["c4_learning_hints_pattern_selection"]["supports_metrics"] == [
        "decision_trace_completeness",
        "planning_validity_rate",
    ]
    assert rows_by_id["c1_c2_c7_scenario_trigger_autonomy"]["claim_ids"] == ["C1", "C2", "C7"]
    assert rows_by_id["c1_c2_c7_scenario_trigger_autonomy"]["summary_kind"] == "scenario_trigger_proof"
    assert rows_by_id["c1_c2_c7_scenario_trigger_autonomy"]["observed_status"] == "passed"
    assert rows_by_id["c1_c2_c7_scenario_trigger_autonomy"]["verification_command"] == [
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/test_scenario_trigger_service.py",
        "tests/test_scenario_registry_service.py",
        "tests/test_api_scenario_registry.py",
    ]
    assert rows_by_id["c1_c2_c7_scenario_trigger_autonomy"]["verification_result"] == "13 passed"
    assert rows_by_id["c8_no_ui_operator_surface"]["claim_ids"] == ["C8-boundary"]
    assert rows_by_id["c8_no_ui_operator_surface"]["baseline"] == "operator_api_smoke"
    assert rows_by_id["c8_no_ui_operator_surface"]["observed_status"] == "passed"

    freeze_report = json.loads(freeze_json_path.read_text(encoding="utf-8"))
    frozen_rows = {row["row_id"]: row for row in freeze_report["rows"]}
    assert frozen_rows["c3_replan_fault_recovery"]["observed_status"] == "passed"
    assert frozen_rows["c3_replan_fault_recovery"]["metrics"]["recovery_success_rate"] == "pass"
    assert frozen_rows["c4_learning_hints_pattern_selection"]["observed_status"] == "passed"
    assert frozen_rows["c4_learning_hints_pattern_selection"]["metrics"]["planning_validity_rate"] == "pass"
    assert frozen_rows["c1_c2_c7_scenario_trigger_autonomy"]["observed_status"] == "passed"
    assert frozen_rows["c1_c2_c7_scenario_trigger_autonomy"]["metrics"]["planning_validity_rate"] == "pass"
    assert frozen_rows["c1_c2_c7_scenario_trigger_autonomy"]["verification_result"] == "13 passed"
    assert frozen_rows["c8_no_ui_operator_surface"]["observed_status"] == "passed"
    assert frozen_rows["c8_no_ui_operator_surface"]["metrics"]["artifact_validity"] == "pass"
    assert all(row["row_id"] != "c1_c2_c7_scenario_trigger_autonomy" for row in freeze_report["failure_rows"])

    markdown = freeze_md_path.read_text(encoding="utf-8")
    assert "c3_replan_fault_recovery" in markdown
    assert "c4_learning_hints_pattern_selection" in markdown
    assert "c1_c2_c7_scenario_trigger_autonomy" in markdown
    assert "c8_no_ui_operator_surface" in markdown
    assert "recovery_success_rate=pass" in markdown
    assert "planning_validity_rate=pass" in markdown
    assert "13 passed" in markdown
    assert "artifact_validity=pass" in markdown
    assert "Water shares the same task-driven runtime and evidence contract after Phase 1 stabilization." in markdown
