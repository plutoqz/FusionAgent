import json
from pathlib import Path

import pytest

from scripts.freeze_research_repeated_protocol_v3 import (
    BATCH_TOKEN_BUDGET,
    PROTOCOL_ID,
    REQUEST_TIMEOUT_SECONDS,
    build_repeated_freeze_v3,
    verify_repeated_freeze_v3,
    write_repeated_freeze_v3,
)
from scripts.run_research_llm_repeated_formal_v3 import validate_repeated_execution_v3


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def _revision_evidence(tmp_path: Path) -> Path:
    path = tmp_path / "model-revision.json"
    path.write_text(
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
    return path


def _ready_freeze(tmp_path: Path) -> Path:
    root = tmp_path / "freeze-v3"
    write_repeated_freeze_v3(
        root,
        build_repeated_freeze_v3(
            manifest_path=MANIFEST,
            implementation_commit="commit-under-test",
            model_revision_evidence_path=_revision_evidence(tmp_path),
        ),
    )
    return root


def _env() -> dict[str, str]:
    return {
        "GEOFUSION_LLM_MODEL": "deepseek-v4-flash",
        "GEOFUSION_LLM_BASE_URL": "https://api.deepseek.com",
        "GEOFUSION_LLM_MAX_OUTPUT_TOKENS": "16384",
        "GEOFUSION_LLM_PILOT_TOKEN_BUDGET": str(BATCH_TOKEN_BUDGET),
        "GEOFUSION_LLM_TIMEOUT_SEC": str(REQUEST_TIMEOUT_SECONDS),
        "GEOFUSION_LLM_API_KEY": "test-secret",
    }


def test_v3_freeze_has_unique_run_ids_timeout_and_no_v2_pooling(tmp_path: Path) -> None:
    root = _ready_freeze(tmp_path)
    protocol = json.loads((root / "formal_protocol.json").read_text(encoding="utf-8"))
    schedule = json.loads((root / "formal_schedule.json").read_text(encoding="utf-8"))
    audit = verify_repeated_freeze_v3(root)

    assert protocol["protocol_id"] == PROTOCOL_ID
    assert protocol["generation"]["request_timeout_seconds"] == REQUEST_TIMEOUT_SECONDS
    assert protocol["design"]["prior_incomplete_results_may_be_pooled"] is False
    assert len(schedule["items"]) == 54
    assert len({item["run_id"] for item in schedule["items"]}) == 54
    assert all(item["run_id"].startswith("formal-v3-") for item in schedule["items"])
    assert audit["passed"] is True


def test_v3_execution_requires_frozen_timeout(tmp_path: Path) -> None:
    root = _ready_freeze(tmp_path)
    protocol = validate_repeated_execution_v3(root, env=_env())
    assert protocol["formal_ready"] is True

    drifted = _env()
    drifted["GEOFUSION_LLM_TIMEOUT_SEC"] = "60"
    with pytest.raises(RuntimeError, match="does not match"):
        validate_repeated_execution_v3(root, env=drifted)


def test_v3_preflight_allows_missing_key_but_execute_gate_does_not(tmp_path: Path) -> None:
    root = _ready_freeze(tmp_path)
    env = _env()
    del env["GEOFUSION_LLM_API_KEY"]

    validate_repeated_execution_v3(root, env=env, require_api_key=False)
    with pytest.raises(RuntimeError, match="api_key"):
        validate_repeated_execution_v3(root, env=env, require_api_key=True)
