from __future__ import annotations

import copy
from pathlib import Path

from scripts.audit_benchmark_platform_protocol import (
    BASE_COMMIT,
    EXPECTED_CLI_COMMANDS,
    EXPECTED_COMPONENT_IDS,
    EXPECTED_FROZEN_INPUTS,
    EXPECTED_MANIFEST_FILES,
    PROTOCOL_ROOT,
    audit_protocol,
    canonical_file_sha256,
    git_blob_sha256,
    hash_entry_map,
    load_json,
    local_markdown_link_errors,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = REPO_ROOT / PROTOCOL_ROOT


def test_all_machine_checks_pass_and_only_human_review_may_remain() -> None:
    result = audit_protocol(REPO_ROOT, ROOT)
    assert set(result["required_failures"]) <= {"human_protocol_review"}
    assert result["accounting"] == {
        "benchmark_instances_generated": 0,
        "provider_calls": 0,
        "judge_calls": 0,
        "formal_result_roots_created": 0,
        "confirmation_unsealed": False,
        "selective_e2e_selected": False,
        "platform_implementation_started": False,
    }


def test_manifest_file_sets_are_complete_and_unique() -> None:
    manifest = load_json(ROOT / "protocol_manifest.json")
    files, file_duplicates = hash_entry_map(manifest["files"])
    frozen, frozen_duplicates = hash_entry_map(manifest["frozen_inputs"])
    assert set(files) == EXPECTED_MANIFEST_FILES
    assert set(frozen) == EXPECTED_FROZEN_INPUTS
    assert file_duplicates == []
    assert frozen_duplicates == []


def test_frozen_inputs_are_bound_to_design_commit() -> None:
    manifest = load_json(ROOT / "protocol_manifest.json")
    for item in manifest["frozen_inputs"]:
        assert git_blob_sha256(REPO_ROOT, BASE_COMMIT, item["path"]) == item["sha256"]


def test_protocol_hashes_detect_tampering(tmp_path: Path) -> None:
    manifest = load_json(ROOT / "protocol_manifest.json")
    for item in manifest["files"]:
        source = REPO_ROOT / item["path"]
        target = tmp_path / item["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        assert canonical_file_sha256(target) == item["sha256"]

    contract = tmp_path / PROTOCOL_ROOT / "component_contract.json"
    contract.write_text(contract.read_text(encoding="utf-8") + "tampered\n", encoding="utf-8")
    expected = next(item["sha256"] for item in manifest["files"] if item["path"].endswith("component_contract.json"))
    assert canonical_file_sha256(contract) != expected


def test_component_and_cli_sets_are_closed() -> None:
    contract = load_json(ROOT / "component_contract.json")
    component_ids = [item["component_id"] for item in contract["components"]]
    assert set(component_ids) == EXPECTED_COMPONENT_IDS
    assert len(component_ids) == len(set(component_ids))
    assert set(contract["allowed_cli_commands"]) == EXPECTED_CLI_COMMANDS
    forbidden = contract["forbidden_cli_tokens"]
    assert all(not any(token in command for token in forbidden) for command in contract["allowed_cli_commands"])
    modules = {item["component_id"]: item["module"] for item in contract["components"]}
    assert modules["BP-STORE"] == "benchmark_platform.store"
    assert modules["BP-CLI"] == "benchmark_platform.cli"


def test_protocol_forbids_implementation_before_approval() -> None:
    contract = load_json(ROOT / "component_contract.json")
    assert contract["implementation_identity"]["authorization_required_after_protocol_freeze"] is True
    assert contract["accounting"]["platform_implementation_started"] is False
    assert not (REPO_ROOT / "benchmark_platform").exists()
    assert "docs/current/benchmark/v1/" in contract["forbidden_change_prefixes"]
    assert "schemas/benchmark.py" in contract["forbidden_change_prefixes"]


def test_accounting_cannot_silently_enable_confirmation() -> None:
    contract = load_json(ROOT / "component_contract.json")
    unsafe = copy.deepcopy(contract["accounting"])
    unsafe["confirmation_unsealed"] = True
    assert unsafe != contract["accounting"]
    assert contract["accounting"]["confirmation_unsealed"] is False
    assert contract["accounting"]["selective_e2e_selected"] is False


def test_protocol_markdown_links_resolve() -> None:
    errors = local_markdown_link_errors(
        [ROOT / "README.md", REPO_ROOT / "docs/current/benchmark-platform-implementation-protocol.md"]
    )
    assert errors == []
