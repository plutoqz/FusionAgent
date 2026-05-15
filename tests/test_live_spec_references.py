from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_live_evidence_ledger_references_existing_spec_files() -> None:
    required_specs = [
        "docs/superpowers/specs/2026-04-08-benchmark-followup-summary.md",
        "docs/superpowers/specs/2026-04-08-building-real-benchmark-result.json",
        "docs/superpowers/specs/2026-04-08-building-micro-benchmark-result.json",
        "docs/superpowers/specs/2026-04-16-building-micro-msft-fresh-checkout-result.json",
        "docs/superpowers/specs/2026-05-09-kg-closure-gates.md",
        "docs/superpowers/specs/2026-05-10-kg-gates-evidence-summary.md",
        "docs/superpowers/specs/2026-05-12-building-gitega-micro-msft-neo4j-baseline-8012.json",
    ]

    for rel_path in required_specs:
        assert (REPO_ROOT / rel_path).exists(), f"Missing live spec: {rel_path}"


def test_specs_readme_indexes_live_benchmark_and_gate_specs() -> None:
    text = (REPO_ROOT / "docs/superpowers/specs/README.md").read_text(encoding="utf-8")

    assert "2026-04-08-benchmark-followup-summary.md" in text
    assert "2026-04-08-building-real-benchmark-result.json" in text
    assert "2026-04-08-building-micro-benchmark-result.json" in text
    assert "2026-04-16-building-micro-msft-fresh-checkout-result.json" in text
    assert "2026-05-09-kg-closure-gates.md" in text
    assert "2026-05-10-kg-gates-evidence-summary.md" in text
    assert "2026-05-12-building-gitega-micro-msft-neo4j-baseline-8012.json" in text


def test_kg_gate_docs_only_link_to_live_micro_baseline_specs() -> None:
    gate_docs = [
        "docs/superpowers/specs/2026-05-09-kg-closure-gates.md",
        "docs/superpowers/specs/2026-05-10-kg-gates-evidence-summary.md",
    ]

    for rel_path in gate_docs:
        text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        assert "docs/superpowers/specs/2026-05-12-building-gitega-micro-msft-neo4j-baseline-8012.json" in text
        assert "docs/superpowers/specs/done/2026-05-12-building-gitega-micro-msft-neo4j-baseline-8012.json" not in text
