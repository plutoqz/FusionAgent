from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
THESIS_DIR = REPO_ROOT / "docs" / "thesis"


def test_thesis_workspace_has_single_entrypoint_and_expected_sections() -> None:
    required_paths = [
        THESIS_DIR / "README.md",
        THESIS_DIR / "experiment-results-draft.md",
        THESIS_DIR / "chapters" / "chapter-01-research-background-draft.md",
        THESIS_DIR / "chapters" / "chapter-02-related-work-draft.md",
        THESIS_DIR / "chapters" / "chapter-03-technical-route-draft.md",
        THESIS_DIR / "chapters" / "chapter-04-experiment-design-draft.md",
        THESIS_DIR / "chapters" / "chapter-05-results-analysis-draft.md",
        THESIS_DIR / "experiments" / "experiment-roadmap.md",
        THESIS_DIR / "experiments" / "next-execution-list.md",
        THESIS_DIR / "evidence" / "evidence-index.md",
    ]

    for path in required_paths:
        assert path.exists(), f"missing thesis workspace file: {path.relative_to(REPO_ROOT)}"

    readme = (THESIS_DIR / "README.md").read_text(encoding="utf-8")
    assert "docs/superpowers/specs" in readme
    assert "C1`, `C2`, and `C3" in readme


def test_thesis_results_draft_labels_controlled_ablation_scope() -> None:
    draft = (THESIS_DIR / "experiment-results-draft.md").read_text(encoding="utf-8")

    assert "exp-ablation-a0-a2-controlled-comparison" in draft
    assert "deterministic counterfactual rows" in draft
    assert "does not run live API, LLM, or KG calls" in draft
    assert "exp-ablation-a0-a2" in draft
    assert "precomputed_artifact_path" in draft


def test_chapter_05_results_draft_combines_controlled_evidence_with_boundaries() -> None:
    draft = (THESIS_DIR / "chapters" / "chapter-05-results-analysis-draft.md").read_text(encoding="utf-8")

    assert "exp-ablation-a0-a2-controlled-comparison" in draft
    assert "2026-06-24-freeze-c-ablation-a0-a2-trace-backed-manifest.json" in draft
    assert "2026-06-24-freeze-c-recovery-governance-manifest.json" in draft
    assert "2026-06-26-freeze-b-caracas-real-evidence-manifest.json" in draft
    assert "4/4` contain the required audit-event chain" in draft
    assert "0/4` artifact files are present" in draft
    assert "B1_bounded_healing_replan_verified" in draft
    assert "G2_replan_limit_fail_closed" in draft
    assert "controlled-ablation-counterfactual-v1" in draft
    assert "Caracas real-data" in draft
    assert "five real-data structural-quality cases" in draft
    assert "Accepted robustness-claim cases" in draft
    assert "Quality-claim cases | 0" in draft
    assert "not a real Benin benchmark replacement" in draft
    assert "E:/fyx/data/Benin" in draft


def test_thesis_evidence_index_references_partial_manifest_and_quality_readiness() -> None:
    index = (THESIS_DIR / "evidence" / "evidence-index.md").read_text(encoding="utf-8")

    assert "2026-06-10-freeze-c-ablation-a0-a2-manifest.json" in index
    assert "2026-06-10-freeze-c-ablation-a0-a2-partial-manifest.json" in index
    assert "2026-06-24-freeze-c-ablation-a0-a2-trace-backed-manifest.json" in index
    assert "2026-06-24-freeze-c-recovery-governance-manifest.json" in index
    assert "2026-06-24-freeze-b-local-blocker-manifest.json" in index
    assert "2026-06-26-freeze-b-caracas-real-evidence-manifest.json" in index
    assert "runs/experiments/exp-quality-freeze-b/readiness.json" in index
    assert "runs/experiments/exp-quality-freeze-b-caracas-real/benchmark_results.json" in index
    assert "not live LLM/API/KG execution" in index
    assert "Not a new statistical benchmark" in index
    assert "Not a benchmark result" in index
