import hashlib
import json
from pathlib import Path

import pytest

from scripts.freeze_research_repeated_extension_protocol import (
    BATCH_TOKEN_BUDGET,
    EXPECTED_CALL_COUNT,
    EXTENSION_REPLICATES,
    PROTOCOL_ID,
    REQUEST_TIMEOUT_SECONDS,
    build_extension_freeze,
    write_extension_freeze,
)
from scripts.run_research_llm_repeated_extension_formal import validate_extension_execution


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-v1.json"


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _base_root(tmp_path: Path) -> Path:
    root = tmp_path / "base-v3"
    for name in ("formal_summary.json", "formal_protocol.json", "schedule.json", "prepared_inputs.json"):
        _write(root / name, {"name": name})
    result_files = []
    for index in range(54):
        run_id = f"formal-v3-fixture-{index:02d}"
        path = root / "runs" / run_id / "result.json"
        _write(path, {"run_id": run_id})
        result_files.append(
            {"run_id": run_id, "path": str(path), "size_bytes": path.stat().st_size, "sha256": _hash(path)}
        )
    audit = {
        "protocol_id": "fusionagent.planning-repeated-formal.v3",
        "model": "deepseek-v4-flash",
        "model_revision": "provider-revision-2026-08-13",
        "evidence_integrity_valid": True,
        "formal_execution_complete": True,
        "scheduled_call_count": 54,
        "extension_gate": {
            "extension_required": True,
            "target_repetitions": 5,
            "scope": "all_cases_and_all_llm_conditions",
            "selective_reruns_allowed": False,
            "reasons": [{"trigger": "multiple_plan_structure_signatures"}],
        },
        "evidence_manifest": {"fixed_files": [], "result_files": result_files},
    }
    _write(root / "formal_automatic_audit.json", audit)
    return root


def _revision_evidence(tmp_path: Path) -> Path:
    path = tmp_path / "model-revision.json"
    _write(
        path,
        {
            "provider": "deepseek_official",
            "model": "deepseek-v4-flash",
            "revision": "provider-revision-2026-08-13",
            "immutable": True,
            "production_release": True,
            "evidence_source": "provider-issued model release record",
            "issued_at": "2026-08-13T00:00:00Z",
        },
    )
    return path


def _freeze(tmp_path: Path) -> tuple[Path, Path]:
    base = _base_root(tmp_path)
    root = tmp_path / "freeze-extension"
    payload = build_extension_freeze(
        manifest_path=MANIFEST,
        base_evidence_root=base,
        implementation_commit="commit-under-test",
        model_revision_evidence_path=_revision_evidence(tmp_path),
    )
    write_extension_freeze(root, payload, base_evidence_root=base)
    return root, base


def _env() -> dict[str, str]:
    return {
        "GEOFUSION_LLM_MODEL": "deepseek-v4-flash",
        "GEOFUSION_LLM_BASE_URL": "https://api.deepseek.com",
        "GEOFUSION_LLM_MAX_OUTPUT_TOKENS": "16384",
        "GEOFUSION_LLM_PILOT_TOKEN_BUDGET": str(BATCH_TOKEN_BUDGET),
        "GEOFUSION_LLM_TIMEOUT_SEC": str(REQUEST_TIMEOUT_SECONDS),
        "GEOFUSION_LLM_API_KEY": "test-secret",
    }


def test_extension_freeze_is_full_grid_repetitions_four_and_five(tmp_path: Path) -> None:
    root, _ = _freeze(tmp_path)
    protocol = json.loads((root / "formal_protocol.json").read_text(encoding="utf-8"))
    schedule = json.loads((root / "formal_schedule.json").read_text(encoding="utf-8"))
    audit = json.loads((root / "freeze_audit.json").read_text(encoding="utf-8"))

    assert protocol["protocol_id"] == PROTOCOL_ID
    assert protocol["formal_ready"] is True
    assert protocol["budget"]["conservative_batch_bound"] <= BATCH_TOKEN_BUDGET
    assert len(schedule["items"]) == EXPECTED_CALL_COUNT
    assert {item["replicate"] for item in schedule["items"]} == set(EXTENSION_REPLICATES)
    assert len({item["run_id"] for item in schedule["items"]}) == EXPECTED_CALL_COUNT
    assert audit["passed"] is True


def test_extension_execution_revalidates_bound_base_and_environment(tmp_path: Path) -> None:
    root, base = _freeze(tmp_path)

    protocol = validate_extension_execution(root, base, env=_env())
    assert protocol["design"]["target_repetitions"] == 5

    drifted = _env()
    drifted["GEOFUSION_LLM_TIMEOUT_SEC"] = "60"
    with pytest.raises(RuntimeError, match="does not match"):
        validate_extension_execution(root, base, env=drifted)

    result = next((base / "runs").glob("*/result.json"))
    result.write_text("{}", encoding="utf-8")
    with pytest.raises(RuntimeError, match="freeze audit failed"):
        validate_extension_execution(root, base, env=_env())
