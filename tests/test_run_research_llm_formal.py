import json
from pathlib import Path

import pytest

from scripts.freeze_research_formal_protocol import build_formal_freeze, write_formal_freeze
from scripts.run_research_llm_formal import validate_formal_execution


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def _ready_freeze(tmp_path: Path) -> Path:
    evidence = {
        "provider": "deepseek_official",
        "model": "deepseek-v4-flash",
        "revision": "provider-revision-2026-08-13",
        "immutable": True,
        "production_release": True,
        "evidence_source": "provider-issued model release record",
        "issued_at": "2026-08-13T00:00:00Z",
    }
    evidence_path = tmp_path / "provider-evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    root = tmp_path / "freeze"
    write_formal_freeze(
        root,
        build_formal_freeze(
            manifest_path=MANIFEST,
            implementation_commit="commit-under-test",
            model_revision_evidence_path=evidence_path,
        ),
    )
    return root


def _env() -> dict[str, str]:
    return {
        "GEOFUSION_LLM_MODEL": "deepseek-v4-flash",
        "GEOFUSION_LLM_BASE_URL": "https://api.deepseek.com",
        "GEOFUSION_LLM_MAX_OUTPUT_TOKENS": "16384",
        "GEOFUSION_LLM_PILOT_TOKEN_BUDGET": "600000",
        "GEOFUSION_LLM_API_KEY": "test-secret",
    }


def test_formal_execution_accepts_only_audited_matching_freeze(tmp_path: Path) -> None:
    protocol = validate_formal_execution(_ready_freeze(tmp_path), env=_env())

    assert protocol["formal_ready"] is True
    assert protocol["provider"]["model_revision"] == "provider-revision-2026-08-13"


def test_formal_execution_rejects_environment_drift(tmp_path: Path) -> None:
    env = _env()
    env["GEOFUSION_LLM_MAX_OUTPUT_TOKENS"] = "8192"

    with pytest.raises(RuntimeError, match="does not match"):
        validate_formal_execution(_ready_freeze(tmp_path), env=env)


def test_formal_execution_rejects_blocked_freeze(tmp_path: Path) -> None:
    root = tmp_path / "blocked"
    write_formal_freeze(
        root,
        build_formal_freeze(manifest_path=MANIFEST, implementation_commit="commit-under-test"),
    )

    with pytest.raises(RuntimeError, match="audit failed"):
        validate_formal_execution(root, env=_env())
