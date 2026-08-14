import json
from pathlib import Path

from scripts.freeze_research_repeated_protocol import build_repeated_freeze, write_repeated_freeze
from scripts.run_research_deterministic_repeated_formal import run_deterministic_repeated


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def test_deterministic_repeated_builds_complete_grid(tmp_path: Path, monkeypatch) -> None:
    evidence_path = tmp_path / "model-revision.json"
    evidence_path.write_text(
        json.dumps(
            {
                "provider": "deepseek_official",
                "model": "deepseek-v4-flash",
                "revision": "provider-revision-2026-08-13",
                "immutable": True,
                "production_release": True,
                "evidence_source": "provider-issued model release record",
                "issued_at": "2026-08-13T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    root = tmp_path / "freeze"
    write_repeated_freeze(
        root,
        build_repeated_freeze(
            manifest_path=MANIFEST,
            implementation_commit="commit-under-test",
            model_revision_evidence_path=evidence_path,
        ),
    )
    monkeypatch.setattr(
        "scripts.run_research_deterministic_repeated_formal.assert_frozen_source_state",
        lambda protocol: None,
    )

    report = run_deterministic_repeated(root, MANIFEST)

    assert report["run_count"] == 54
    assert report["repetitions"] == 3
    assert {row["replicate"] for row in report["runs"]} == {1, 2, 3}
    for case_id in ("C01", "C02", "C03", "C04", "C05", "C06"):
        for group in ("fixed_workflow", "rules_only", "kg_only"):
            hashes = {
                row["output_hash"]
                for row in report["runs"]
                if row["case_id"] == case_id and row["group"] == group
            }
            assert len(hashes) == 1
