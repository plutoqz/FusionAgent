from pathlib import Path

from scripts.run_no_ui_maturity_check import (
    DEFAULT_REQUIRED_FILES,
    build_summary,
    collect_readme_stale_wording_status,
    collect_static_maturity_status,
)


def test_collect_static_maturity_status_reports_required_docs(tmp_path: Path) -> None:
    required = tmp_path / "target.md"
    required.write_text("ok", encoding="utf-8")

    status = collect_static_maturity_status([required])

    assert status["required_files"][str(required)] is True


def test_collect_static_maturity_status_reports_missing_required_docs(
    tmp_path: Path,
) -> None:
    required = tmp_path / "missing-target.md"

    status = collect_static_maturity_status([required])

    assert status["required_files"][str(required)] is False


def test_default_required_files_include_operator_read_model_contract() -> None:
    contract_suffix = (
        "docs/superpowers/specs/2026-04-21-operator-read-model-contract.md"
    )

    assert any(
        path.as_posix().endswith(contract_suffix)
        for path in DEFAULT_REQUIRED_FILES
    )


def test_readme_stale_wording_detects_only_a_prototype(
    tmp_path: Path,
) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("This project is only a prototype for now.", encoding="utf-8")

    status = collect_readme_stale_wording_status([readme])

    assert status["stale_readme_phrases"][str(readme)] == ["only a prototype"]


def test_readme_stale_wording_is_pending_without_maturity_markers(
    tmp_path: Path,
) -> None:
    readme = tmp_path / "README.md"
    readme.write_text("This project is prototype only for now.", encoding="utf-8")

    status = collect_readme_stale_wording_status([readme])

    assert status["readme_wording_passed"] is True
    assert status["readme_repositioning_status"] == "pending"
    assert status["readme_repositioning_complete"] is False
    assert status["stale_readme_phrases"][str(readme)] == ["prototype only"]


def test_readme_stale_wording_fails_when_maturity_markers_exist(
    tmp_path: Path,
) -> None:
    readme = tmp_path / "README.en.md"
    readme.write_text(
        "Mature no-UI vector data fusion agent: reached.\n"
        "This project is prototype only for now.",
        encoding="utf-8",
    )

    status = collect_readme_stale_wording_status([readme])

    assert status["readme_wording_passed"] is False
    assert status["readme_repositioning_status"] == "enforced"
    assert status["readme_repositioning_complete"] is True
    assert status["stale_readme_phrases"][str(readme)] == ["prototype only"]


def test_readme_repositioning_requires_all_checked_readmes_to_have_markers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    present = tmp_path / "present.md"
    readme_cn = tmp_path / "README.md"
    readme_en = tmp_path / "README.en.md"
    present.write_text("ok", encoding="utf-8")
    readme_cn.write_text("这是中性说明，没有 maturity marker。", encoding="utf-8")
    readme_en.write_text(
        "Mature no-UI vector data fusion agent: reached.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scripts.run_no_ui_maturity_check.DEFAULT_REQUIRED_FILES",
        [present],
    )
    monkeypatch.setattr(
        "scripts.run_no_ui_maturity_check.README_FILES",
        [readme_cn, readme_en],
    )

    status = collect_readme_stale_wording_status([readme_cn, readme_en])
    summary = build_summary(run_tests=False, require_readme_repositioning=True)

    assert status["readme_repositioning_complete"] is False
    assert status["readme_maturity_markers"][str(readme_cn)] == []
    assert status["readme_maturity_markers"][str(readme_en)] == [
        "Mature no-UI vector data fusion agent: reached"
    ]
    assert summary["static"]["readme_repositioning_complete"] is False
    assert summary["maturity_gate_passed"] is False
    assert summary["passed"] is False


def test_readme_opening_prototype_wording_fails_when_maturity_markers_exist(
    tmp_path: Path,
) -> None:
    readme = tmp_path / "README.en.md"
    readme.write_text(
        "Mature no-UI vector data fusion agent: reached.\n"
        "FusionAgent is a vector-data fusion agent prototype for disaster response workflows.",
        encoding="utf-8",
    )

    status = collect_readme_stale_wording_status([readme])

    assert status["readme_wording_passed"] is False
    assert status["readme_repositioning_status"] == "enforced"
    assert status["stale_readme_phrases"][str(readme)] == [
        "agent prototype opening"
    ]


def test_readme_historical_agent_prototype_reference_does_not_count_as_opening(
    tmp_path: Path,
) -> None:
    readme = tmp_path / "README.en.md"
    readme.write_text(
        "Mature no-UI vector data fusion agent: reached.\n"
        "Early drafts called it an agent prototype before the maturity work landed.",
        encoding="utf-8",
    )

    status = collect_readme_stale_wording_status([readme])

    assert status["readme_wording_passed"] is True
    assert status["stale_readme_phrases"][str(readme)] == []


def test_readme_subject_led_historical_prototype_reference_is_not_opening(
    tmp_path: Path,
) -> None:
    readme = tmp_path / "README.en.md"
    readme.write_text(
        "Mature no-UI vector data fusion agent: reached.\n"
        "This project was once described as an agent prototype during early exploration.",
        encoding="utf-8",
    )

    status = collect_readme_stale_wording_status([readme])

    assert status["readme_wording_passed"] is True
    assert status["stale_readme_phrases"][str(readme)] == []


def test_readme_archive_example_prototype_reference_is_not_opening(
    tmp_path: Path,
) -> None:
    readme = tmp_path / "README.en.md"
    readme.write_text(
        "Mature no-UI vector data fusion agent: reached.\n"
        "FusionAgent is an agent prototype used in the 2024 archive example.",
        encoding="utf-8",
    )

    status = collect_readme_stale_wording_status([readme])

    assert status["readme_wording_passed"] is True
    assert status["stale_readme_phrases"][str(readme)] == []


def test_readme_negated_agent_prototype_reference_is_not_opening(
    tmp_path: Path,
) -> None:
    readme = tmp_path / "README.en.md"
    readme.write_text(
        "Mature no-UI vector data fusion agent: reached.\n"
        "This project is no longer an agent prototype.",
        encoding="utf-8",
    )

    status = collect_readme_stale_wording_status([readme])

    assert status["readme_wording_passed"] is True
    assert status["stale_readme_phrases"][str(readme)] == []


def test_readme_historical_agent_prototype_heading_is_not_opening(
    tmp_path: Path,
) -> None:
    readme = tmp_path / "README.en.md"
    readme.write_text(
        "Mature no-UI vector data fusion agent: reached.\n"
        "## Historical agent prototype references",
        encoding="utf-8",
    )

    status = collect_readme_stale_wording_status([readme])

    assert status["readme_wording_passed"] is True
    assert status["stale_readme_phrases"][str(readme)] == []


def test_readme_heading_agent_prototype_reference_still_counts_as_opening(
    tmp_path: Path,
) -> None:
    readme = tmp_path / "README.en.md"
    readme.write_text(
        "Mature no-UI vector data fusion agent: reached.\n"
        "# FusionAgent is an agent prototype for disaster response workflows.",
        encoding="utf-8",
    )

    status = collect_readme_stale_wording_status([readme])

    assert status["readme_wording_passed"] is False
    assert status["stale_readme_phrases"][str(readme)] == [
        "agent prototype opening"
    ]


def test_readme_first_sentence_agent_prototype_reference_still_counts_as_opening(
    tmp_path: Path,
) -> None:
    readme = tmp_path / "README.en.md"
    readme.write_text(
        "Mature no-UI vector data fusion agent: reached.\n"
        "FusionAgent is an agent prototype for disaster response workflows.",
        encoding="utf-8",
    )

    status = collect_readme_stale_wording_status([readme])

    assert status["readme_wording_passed"] is False
    assert status["stale_readme_phrases"][str(readme)] == [
        "agent prototype opening"
    ]


def test_readme_used_in_production_agent_prototype_reference_counts_as_opening(
    tmp_path: Path,
) -> None:
    readme = tmp_path / "README.en.md"
    readme.write_text(
        "Mature no-UI vector data fusion agent: reached.\n"
        "FusionAgent is an agent prototype used in production workflows.",
        encoding="utf-8",
    )

    status = collect_readme_stale_wording_status([readme])

    assert status["readme_wording_passed"] is False
    assert status["stale_readme_phrases"][str(readme)] == [
        "agent prototype opening"
    ]


def test_build_summary_marks_pending_readme_without_failing_static_check(
    tmp_path: Path,
    monkeypatch,
) -> None:
    present = tmp_path / "present.md"
    readme = tmp_path / "README.md"
    present.write_text("ok", encoding="utf-8")
    readme.write_text("This project is prototype only for now.", encoding="utf-8")
    monkeypatch.setattr(
        "scripts.run_no_ui_maturity_check.DEFAULT_REQUIRED_FILES",
        [present],
    )
    monkeypatch.setattr("scripts.run_no_ui_maturity_check.README_FILES", [readme])

    summary = build_summary(run_tests=False)

    assert summary["passed"] is True
    assert summary["static_check_passed"] is True
    assert summary["maturity_gate_passed"] is False
    assert summary["static"]["readme_repositioning_status"] == "pending"
    assert summary["static"]["readme_repositioning_complete"] is False


def test_build_summary_can_require_readme_repositioning(
    tmp_path: Path,
    monkeypatch,
) -> None:
    present = tmp_path / "present.md"
    readme = tmp_path / "README.md"
    present.write_text("ok", encoding="utf-8")
    readme.write_text("This project is prototype only for now.", encoding="utf-8")
    monkeypatch.setattr(
        "scripts.run_no_ui_maturity_check.DEFAULT_REQUIRED_FILES",
        [present],
    )
    monkeypatch.setattr("scripts.run_no_ui_maturity_check.README_FILES", [readme])

    summary = build_summary(run_tests=False, require_readme_repositioning=True)

    assert summary["passed"] is False
    assert summary["readme_repositioning_required"] is True
    assert summary["static_check_passed"] is True
    assert summary["maturity_gate_passed"] is False


def test_build_summary_aggregates_static_readme_and_skipped_tests(
    tmp_path: Path,
    monkeypatch,
) -> None:
    present = tmp_path / "present.md"
    missing = tmp_path / "missing.md"
    readme = tmp_path / "README.md"
    present.write_text("ok", encoding="utf-8")
    readme.write_text(
        "No-UI mature vector data fusion agent: achieved.\n"
        "This project is only a prototype for now.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scripts.run_no_ui_maturity_check.DEFAULT_REQUIRED_FILES",
        [present, missing],
    )
    monkeypatch.setattr("scripts.run_no_ui_maturity_check.README_FILES", [readme])

    summary = build_summary(run_tests=False)

    assert summary["passed"] is False
    assert summary["static_check_passed"] is False
    assert summary["maturity_gate_passed"] is False
    assert summary["static"]["required_files"][str(present)] is True
    assert summary["static"]["required_files"][str(missing)] is False
    assert summary["static"]["required_files_passed"] is False
    assert summary["static"]["readme_wording_passed"] is False
    assert summary["static"]["stale_readme_phrases"][str(readme)] == [
        "only a prototype"
    ]
    assert summary["tests"] == {"skipped": True}


def test_no_ui_runbooks_keep_local_inbox_supported_and_external_event_feed_replay_rejected() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    no_ui_runbook = (repo_root / "docs" / "no-ui-agent-operations.md").read_text(encoding="utf-8").lower()
    v2_ops = (repo_root / "docs" / "v2-operations.md").read_text(encoding="utf-8").lower()

    assert "local file inbox is the supported no-ui trigger" in no_ui_runbook
    assert "external event-feed replay is not supported" in no_ui_runbook
    assert "local file inbox remains the supported no-ui trigger path" in v2_ops
    assert "external event-feed replay is not supported in this phase" in v2_ops
