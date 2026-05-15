from pathlib import Path
import json
import re


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

    assert "2026-04-07-real-data-eval-manifest.json" in text
    assert "2026-04-07-fusion-agent-v2-design.md" in text
    assert "2026-04-08-benchmark-followup-summary.md" in text
    assert "2026-04-08-building-real-benchmark-result.json" in text
    assert "2026-04-08-building-micro-benchmark-result.json" in text
    assert "2026-04-10-thesis-aligned-agent-design.md" in text
    assert "2026-04-16-building-micro-alignment-result.json" in text
    assert "2026-04-16-building-micro-msft-fresh-checkout-result.json" in text
    assert "2026-04-17-agentic-any-region-fusion-design.md" in text
    assert "2026-04-23-system-next-improvement-review.md" in text
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


def test_live_paper_evidence_chain_does_not_use_done_plan_paths() -> None:
    live_text_docs = [
        "docs/superpowers/specs/2026-04-20-evidence-ledger.md",
        "docs/superpowers/specs/2026-04-21-paper-evidence-freeze.md",
    ]
    live_json_docs = [
        "docs/superpowers/specs/2026-04-21-paper-experiment-matrix.json",
        "docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json",
    ]

    for rel_path in live_text_docs:
        text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
        assert "docs/superpowers/plans/done/" not in text, f"Live doc still depends on done/: {rel_path}"

    for rel_path in live_json_docs:
        payload = json.loads((REPO_ROOT / rel_path).read_text(encoding="utf-8"))
        serialized = json.dumps(payload, ensure_ascii=False)
        assert "docs/superpowers/plans/done/" not in serialized, f"Live doc still depends on done/: {rel_path}"


def test_repo_paper_evidence_freeze_manifest_is_repo_relative() -> None:
    freeze_report = json.loads(
        (REPO_ROOT / "docs/superpowers/specs/2026-04-21-paper-evidence-freeze.json").read_text(
            encoding="utf-8"
        )
    )
    first_row = next(row for row in freeze_report["rows"] if row["row_id"] == "c1_c2_building_google_full_system")
    assert first_row["manifest"] == "docs/superpowers/specs/2026-04-07-real-data-eval-manifest.json"


def test_live_spec_markdown_references_resolve_inside_live_specs_root() -> None:
    root = REPO_ROOT / "docs/superpowers/specs"
    pattern = re.compile(r"docs/superpowers/specs/[A-Za-z0-9._/\-]+")

    for path in root.glob("*.md"):
        text = path.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            referenced = match.group(0).replace("\\", "/")
            assert (REPO_ROOT / referenced).exists(), (
                f"Live spec reference does not exist in live root: {referenced} "
                f"(referenced from {path.relative_to(REPO_ROOT).as_posix()})"
            )
