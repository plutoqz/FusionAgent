from pathlib import Path

from scripts.run_research_deterministic_formal import run_deterministic_formal


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def test_deterministic_formal_runs_six_cases_by_three_groups() -> None:
    report = run_deterministic_formal(MANIFEST)

    assert report["run_count"] == 18
    assert report["implementation_hashes"]
    assert {row["group"] for row in report["runs"]} == {
        "fixed_workflow",
        "rules_only",
        "kg_only",
    }
    assert all(row["evaluation"]["pre_fallback_valid"] for row in report["runs"])
    assert all(row["input_hash"].startswith("sha256:") for row in report["runs"])
    assert all(row["output_hash"].startswith("sha256:") for row in report["runs"])
