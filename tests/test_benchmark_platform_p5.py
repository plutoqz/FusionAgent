from __future__ import annotations

import json
from pathlib import Path

import pytest

from benchmark_platform.canonical import canonical_sha256
from benchmark_platform.store import ArtifactStore, ResumeRequest, RunBinding, StoreError


def binding() -> RunBinding:
    return RunBinding(
        run_id="BDV1-DEV-P5-000",
        design_id="fusionagent.benchmark-design.v1",
        design_sha256="sha256:" + "1" * 64,
        template_sha256="sha256:" + "2" * 64,
        seed_namespace="fusionagent-benchmark-v1-development",
        master_seed=2026081901,
        code_revision="p5-contract-test",
        input_hashes={"design": "sha256:" + "3" * 64, "template": "sha256:" + "4" * 64},
    )


def generated_store(tmp_path: Path) -> ArtifactStore:
    store = ArtifactStore.create_new(tmp_path / "run", binding())
    store.commit_stage("design_bound", input_hashes={"design": binding().design_sha256}, output_paths=["design_binding.json"])
    store.write_json_artifact("template_snapshots/fixture.json", {"template": "fixture"})
    store.commit_stage("templates_validated", input_hashes={"template": binding().template_sha256}, output_paths=["template_snapshots/fixture.json"])
    instance = {"instance_id": "BDV1-DEV-BC-CAUSAL-01-000", "instance_sha256": canonical_sha256({"member": 1})}
    store.append_jsonl("generation_attempts.jsonl", {"attempt_index": 0, "status": "valid"})
    store.append_instance(instance)
    store.commit_stage("generated", input_hashes={"generator": "sha256:" + "5" * 64}, output_paths=["generation_attempts.jsonl", "instances.jsonl"])
    return store


def complete_store(store: ArtifactStore) -> None:
    store.write_json_artifact("validation_report.json", {"relations": "passed"})
    store.commit_stage("relations_validated", input_hashes={"relations": "sha256:" + "6" * 64}, output_paths=["validation_report.json"])
    store.append_jsonl("planner_packets.jsonl", {"packet": "planner"})
    store.append_jsonl("evaluator_packets.jsonl", {"packet": "evaluator"})
    store.append_jsonl("human_blind_packets.jsonl", {"packet": "blind"})
    store.write_json_artifact("leakage_audit.json", {"passed": True})
    store.commit_stage("views_projected", input_hashes={"views": "sha256:" + "7" * 64}, output_paths=["planner_packets.jsonl", "evaluator_packets.jsonl", "human_blind_packets.jsonl", "leakage_audit.json"])
    store.write_json_artifact("validation_report.json", {"relations": "passed", "audit": "passed"})
    store.commit_stage("audited", input_hashes={"audit": "sha256:" + "8" * 64}, output_paths=["validation_report.json"])
    store.commit_stage("development_complete", input_hashes={"completion": "sha256:" + "9" * 64}, output_paths=[])


def test_write_new_root_is_atomic_and_refuses_existing_root(tmp_path: Path) -> None:
    store = ArtifactStore.create_new(tmp_path / "run", binding())
    assert (store.root / "checkpoint.json").is_file()
    assert (store.root / "template_snapshots").is_dir()
    with pytest.raises(StoreError) as error:
        ArtifactStore.create_new(tmp_path / "run", binding())
    assert error.value.failures[0].details["code"] == "store.output_exists"


def test_interrupted_run_resumes_from_latest_checkpoint_without_duplicate_instance(tmp_path: Path) -> None:
    store = generated_store(tmp_path)
    state = store.resume(ResumeRequest(run_root=str(store.root), expected_stage="generated", binding=binding()))
    assert state.stage == "generated"
    lines = (store.root / "instances.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["instance_id"] == "BDV1-DEV-BC-CAUSAL-01-000"
    with pytest.raises(StoreError) as error:
        store.append_instance(json.loads(lines[0]))
    assert error.value.failures[0].details["code"] == "store.output_exists"
    assert len((store.root / "instances.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_resume_fails_closed_when_retained_output_or_binding_drifts(tmp_path: Path) -> None:
    store = generated_store(tmp_path)
    (store.root / "instances.jsonl").write_text("{\"tampered\":true}\n", encoding="utf-8")
    with pytest.raises(StoreError) as error:
        store.resume(ResumeRequest(run_root=str(store.root), expected_stage="generated", binding=binding()))
    assert error.value.failures[0].details["code"] == "store.resume_hash_drift"

    clean = generated_store(tmp_path / "clean")
    changed = binding().model_copy(update={"code_revision": "changed"})
    with pytest.raises(StoreError) as error:
        clean.resume(ResumeRequest(run_root=str(clean.root), expected_stage="generated", binding=changed))
    assert error.value.failures[0].details["code"] == "store.resume_hash_drift"


def test_terminal_checksums_are_externally_bound_and_verify_all_other_files(tmp_path: Path) -> None:
    store = generated_store(tmp_path)
    complete_store(store)
    terminal = store.finalize()
    assert terminal.covered_file_count > 1
    assert store.verify_terminal(terminal) is True
    (store.root / "validation_report.json").write_text("{}", encoding="utf-8")
    assert store.verify_terminal(terminal) is False
