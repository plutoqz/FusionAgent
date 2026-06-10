from pathlib import Path


def test_handshake_doc_separates_research_plan_and_capability_plan() -> None:
    text = Path(
        "docs/superpowers/specs/2026-05-13-thesis-capability-handshake.md"
    ).read_text(encoding="utf-8")

    assert "research plan answers why and how to prove" in text
    assert "capability plan answers what to freeze and what to harden" in text
    assert "The thesis narrative must not outrun Phase A-D." in text


def test_specs_readme_lists_new_thesis_live_docs() -> None:
    text = Path("docs/superpowers/specs/README.md").read_text(encoding="utf-8")

    assert "2026-05-13-thesis-research-spec.md" in text
    assert "2026-05-13-thesis-claims-ledger.md" in text
    assert "2026-05-13-thesis-related-work-matrix.json" in text
    assert "2026-05-13-thesis-outline-and-timeline.md" in text
    assert "2026-05-13-thesis-capability-handshake.md" in text


def test_completed_master_plan_is_archived_and_only_roadmap_plans_are_active() -> None:
    plans_root = Path("docs/superpowers/plans")
    active_plans = sorted(path.name for path in plans_root.glob("*.md"))

    assert active_plans == [
        "2026-06-10-plan-a-algorithm-trust-runtime-contract-freeze.md",
        "2026-06-10-plan-b-benchmark-protocol-quality-evaluation-freeze.md",
        "2026-06-10-plan-c-architecture-mvp-ablation-harness.md",
        "2026-06-10-plan-d-freeze-c-evidence-thesis-closure.md",
        "2026-06-10-plan-e-windows-runtime-operability-long-run.md",
    ]
    assert (plans_root / "done" / "2026-05-13-fusionagent-master-execution-plan.md").exists()
