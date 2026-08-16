import json
from pathlib import Path

from kg.knowledge_release import semantic_hash
from scripts.run_research_method_b_formal import PROTOCOL_ID as BASE_PROTOCOL_ID
from scripts.run_research_method_b_formal import prepare_formal_inputs
from scripts.run_research_method_b_repair_formal import (
    BASELINE_CONDITIONS,
    METHOD_B_CONDITION,
    build_freeze,
    prepare_repair_inputs,
)


MANIFEST = Path(__file__).parents[1] / "docs" / "current" / "research-case-manifest-heldout-method-b-v1.json"


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def _base_evidence(tmp_path: Path) -> Path:
    root = tmp_path / "base"
    schedule, prepared = prepare_formal_inputs(MANIFEST)
    protocol = {
        "protocol_id": BASE_PROTOCOL_ID,
        "implementation_commit": "base-commit",
        "identities": {
            "schedule_sha256": semantic_hash(schedule),
            "prepared_inputs_sha256": semantic_hash(prepared),
        },
    }
    _write_json(root / "formal_protocol.json", protocol)
    _write_json(root / "schedule.json", schedule)
    _write_json(root / "prepared_inputs.json", prepared)
    for item in prepared:
        run_id = item["schedule"]["run_id"]
        _write_json(root / "runs" / run_id / "result.json", {"run_id": run_id, "success": True})
    return root


def test_repair_preparation_reuses_unchanged_baselines_and_reruns_all_method_b_cells(tmp_path: Path) -> None:
    base_root = _base_evidence(tmp_path)

    schedule, prepared, binding = prepare_repair_inputs(MANIFEST, base_root)

    assert len(schedule["items"]) == len(prepared) == 18
    assert schedule["knowledge_conditions"] == [METHOD_B_CONDITION]
    assert {item["schedule"]["knowledge_condition"] for item in prepared} == {METHOD_B_CONDITION}
    assert binding["baseline_conditions"] == sorted(BASELINE_CONDITIONS)
    assert binding["baseline_call_count"] == 36
    assert binding["baseline_input_hashes_unchanged"] is True
    assert len(binding["baseline_result_file_hashes"]) == 36


def test_repair_protocol_records_post_heldout_boundary_and_bounded_paid_grid(tmp_path: Path) -> None:
    base_root = _base_evidence(tmp_path)
    revision_path = tmp_path / "revision.json"
    _write_json(revision_path, {"revision": "test-revision"})

    protocol, schedule, prepared, _ = build_freeze(
        manifest_path=MANIFEST,
        base_evidence_root=base_root,
        implementation_commit="repair-commit",
        model_revision_evidence_path=revision_path,
    )

    assert protocol["repair"]["post_heldout_intervention"] is True
    assert protocol["repair"]["case_specific_logic_added"] is False
    assert protocol["design"]["new_paid_call_count"] == 18
    assert protocol["design"]["reused_read_only_baseline_calls"] == 36
    assert protocol["budget"]["bound_within_budget"] is True
    assert len(schedule["items"]) == len(prepared) == 18
