import json
from pathlib import Path

from scripts.audit_research_deterministic_repeated import audit_deterministic_repeated
from scripts.freeze_research_repeated_protocol import build_repeated_freeze, write_repeated_freeze
from scripts.run_research_deterministic_repeated_formal import run_deterministic_repeated

MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def test_audit_accepts_complete_stable_grid(tmp_path, monkeypatch) -> None:
    evidence_path = tmp_path / "model-revision.json"
    evidence_path.write_text(
        '{"provider":"deepseek_official","model":"deepseek-v4-flash",'
        '"revision":"provider-revision-2026-08-13","immutable":true,'
        '"production_release":true,"evidence_source":"provider record",'
        '"issued_at":"2026-08-13T00:00:00Z"}',
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
    monkeypatch.setattr(
        "scripts.run_research_deterministic_repeated_formal._git_head",
        lambda: "a" * 40,
    )
    result = tmp_path / "deterministic.json"
    result.write_text(
        json.dumps(run_deterministic_repeated(root, MANIFEST)),
        encoding="utf-8",
    )

    audit = audit_deterministic_repeated(result)

    assert audit["passed"] is True
    assert audit["run_count"] == 54
    assert audit["cell_count"] == 18
    assert all(audit["checks"].values())
