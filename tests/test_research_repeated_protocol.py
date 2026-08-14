import json
from pathlib import Path

import pytest

from schemas.research_llm_pilot import build_research_llm_repeated_schedule
from scripts.freeze_research_repeated_protocol import (
    BATCH_TOKEN_BUDGET,
    build_repeated_freeze,
    verify_repeated_freeze,
    write_repeated_freeze,
)
from scripts.run_research_llm_repeated_formal import validate_repeated_execution


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
    root = tmp_path / "freeze"
    write_repeated_freeze(
        root,
        build_repeated_freeze(
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
        "GEOFUSION_LLM_API_KEY": "test-secret",
    }


def test_repeated_schedule_has_three_complete_shuffled_repetitions() -> None:
    first = build_research_llm_repeated_schedule(schedule_seed=20260814, replicates=3)
    second = build_research_llm_repeated_schedule(schedule_seed=20260814, replicates=3)

    assert [item.run_id for item in first.items] == [item.run_id for item in second.items]
    assert len(first.items) == 54
    assert {item.replicate for item in first.items} == {1, 2, 3}
    assert len({item.run_id for item in first.items}) == 54
    assert first.metadata["statistical_significance_claim_eligible"] is False


def test_repeated_schedule_rejects_single_repetition() -> None:
    with pytest.raises(ValueError, match="at least two"):
        build_research_llm_repeated_schedule(schedule_seed=20260814, replicates=1)


def test_repeated_freeze_hashes_54_calls_and_forbids_v1_pooling(tmp_path: Path) -> None:
    root = _ready_freeze(tmp_path)
    protocol = json.loads((root / "formal_protocol.json").read_text(encoding="utf-8"))
    audit = verify_repeated_freeze(root)

    assert protocol["design"]["llm_call_count"] == 54
    assert protocol["design"]["deterministic_run_count"] == 54
    assert protocol["design"]["old_v1_results_may_be_pooled"] is False
    assert protocol["budget"]["bound_within_budget"] is True
    assert protocol["replication_policy"]["selective_reruns_for_failed_or_low_scoring_cells"] == "forbidden"
    assert audit["passed"] is True


def test_repeated_execution_requires_exact_environment(tmp_path: Path) -> None:
    root = _ready_freeze(tmp_path)
    protocol = validate_repeated_execution(root, env=_env())
    assert protocol["formal_ready"] is True

    drifted = _env()
    drifted["GEOFUSION_LLM_PILOT_TOKEN_BUDGET"] = "600000"
    with pytest.raises(RuntimeError, match="does not match"):
        validate_repeated_execution(root, env=drifted)


def test_repeated_preflight_allows_missing_key_but_execute_gate_does_not(tmp_path: Path) -> None:
    root = _ready_freeze(tmp_path)
    env = _env()
    del env["GEOFUSION_LLM_API_KEY"]

    protocol = validate_repeated_execution(root, env=env, require_api_key=False)
    assert protocol["formal_ready"] is True
    with pytest.raises(RuntimeError, match="api_key"):
        validate_repeated_execution(root, env=env, require_api_key=True)
