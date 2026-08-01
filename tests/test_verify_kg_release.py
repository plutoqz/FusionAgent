from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_kg_release.py"
FROZEN_RELEASE = ROOT / "kg" / "ontology" / "v1.0.0"


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _semantic_hash(release_dir: Path) -> str:
    payloads = [
        json.loads((release_dir / filename).read_text(encoding="utf-8"))
        for filename in ("schema.json", "entities.json", "policies.json")
    ]
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(payloads)).hexdigest()


def _seal_entities(entities: dict[str, Any]) -> None:
    normalized = json.loads(json.dumps(entities, ensure_ascii=False, sort_keys=True))
    normalized["metadata"]["content_hash"] = ""
    normalized["metadata"]["generated_at"] = ""
    entities["metadata"]["content_hash"] = (
        "sha256:" + hashlib.sha256(_canonical_json_bytes(normalized)).hexdigest()
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _refresh_release_hashes(release_dir: Path) -> None:
    release_path = release_dir / "release.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    for filename in ("schema.json", "entities.json", "policies.json"):
        release["files"][filename] = _sha256_file(release_dir / filename)
    release["semantic_hash"] = _semantic_hash(release_dir)
    _write_json(release_path, release)


def _copy_release(tmp_path: Path) -> Path:
    target = tmp_path / "release"
    shutil.copytree(FROZEN_RELEASE, target)
    return target


def _run_verifier(
    release_dir: Path, report_path: Path
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--release-dir",
            str(release_dir),
            "--report-path",
            str(report_path),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert report_path.is_file(), result.stdout + result.stderr
    report = json.loads(report_path.read_text(encoding="utf-8"))
    return result, report


def _check(report: dict[str, Any], check_id: str) -> dict[str, Any]:
    return next(item for item in report["checks"] if item["id"] == check_id)


def test_verifier_has_no_runtime_seed_dependency() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "kg.seed" not in source
    assert "from kg" not in source
    assert "import kg" not in source


def test_clean_frozen_release_passes_independent_verification(tmp_path: Path) -> None:
    release_dir = _copy_release(tmp_path)
    report_path = tmp_path / "verification_report.json"

    result, report = _run_verifier(release_dir, report_path)

    assert result.returncode == 0, result.stdout + result.stderr
    assert report["passed"] is True
    assert report["summary"]["failed_count"] == 0
    assert report["release_identity"]["release_id"] == "fusionagent-kg-v1.0.0"


@pytest.mark.parametrize("filename", ["schema.json", "entities.json", "policies.json"])
def test_one_byte_change_in_any_frozen_payload_fails(
    tmp_path: Path,
    filename: str,
) -> None:
    release_dir = _copy_release(tmp_path)
    target = release_dir / filename
    raw = bytearray(target.read_bytes())
    assert raw[-1] == ord("\n")
    raw[-1] = ord(" ")
    target.write_bytes(raw)
    report_path = tmp_path / "verification_report.json"

    result, report = _run_verifier(release_dir, report_path)

    assert result.returncode != 0
    assert report["passed"] is False
    hash_check = _check(report, "file_hashes")
    assert hash_check["passed"] is False
    assert any(filename in error for error in hash_check["errors"])


def test_missing_required_entity_reference_fails_after_hashes_are_resealed(
    tmp_path: Path,
) -> None:
    release_dir = _copy_release(tmp_path)
    entities_path = release_dir / "entities.json"
    entities = json.loads(entities_path.read_text(encoding="utf-8"))
    entities["data_needs"][0]["data_type_id"] = "dt.missing.required-reference"
    _seal_entities(entities)
    _write_json(entities_path, entities)
    _refresh_release_hashes(release_dir)
    report_path = tmp_path / "verification_report.json"

    result, report = _run_verifier(release_dir, report_path)

    assert result.returncode != 0
    assert _check(report, "file_hashes")["passed"] is True
    assert _check(report, "semantic_hash")["passed"] is True
    closure_check = _check(report, "entity_reference_closure")
    assert closure_check["passed"] is False
    assert any(
        "dt.missing.required-reference" in error for error in closure_check["errors"]
    )


def test_missing_required_competency_question_fails_after_hashes_are_resealed(
    tmp_path: Path,
) -> None:
    release_dir = _copy_release(tmp_path)
    schema_path = release_dir / "schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema["competency_questions"] = [
        question
        for question in schema["competency_questions"]
        if question["id"] != "CQ08"
    ]
    _write_json(schema_path, schema)
    _refresh_release_hashes(release_dir)
    report_path = tmp_path / "verification_report.json"

    result, report = _run_verifier(release_dir, report_path)

    assert result.returncode != 0
    assert _check(report, "file_hashes")["passed"] is True
    assert _check(report, "semantic_hash")["passed"] is True
    cq_check = _check(report, "competency_questions")
    assert cq_check["passed"] is False
    assert any("CQ08" in error for error in cq_check["errors"])


def test_cross_type_source_fallback_fails_after_hashes_are_resealed(tmp_path: Path) -> None:
    release_dir = _copy_release(tmp_path)
    policies_path = release_dir / "policies.json"
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    waterways = next(
        item
        for item in policies["source_bundle_policies"]
        if item["source_id"] == "catalog.flood.waterways"
    )
    waterways["fallback_source_ids"] = ["catalog.flood.water"]
    _write_json(policies_path, policies)
    _refresh_release_hashes(release_dir)
    report_path = tmp_path / "verification_report.json"

    result, report = _run_verifier(release_dir, report_path)

    assert result.returncode != 0
    closure_check = _check(report, "policy_reference_closure")
    assert closure_check["passed"] is False
    assert any("I/O 类型不闭合" in error for error in closure_check["errors"])


def test_runtime_source_alias_to_unknown_entity_fails_after_reseal(tmp_path: Path) -> None:
    release_dir = _copy_release(tmp_path)
    policies_path = release_dir / "policies.json"
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    policies["source_runtime_bindings"]["source_id_aliases"]["raw.legacy"] = "raw.missing"
    _write_json(policies_path, policies)
    _refresh_release_hashes(release_dir)
    report_path = tmp_path / "verification_report.json"

    result, report = _run_verifier(release_dir, report_path)

    assert result.returncode != 0
    closure_check = _check(report, "policy_reference_closure")
    assert closure_check["passed"] is False
    assert any("raw.missing" in error for error in closure_check["errors"])


def test_missing_failure_classification_policy_fails_after_reseal(tmp_path: Path) -> None:
    release_dir = _copy_release(tmp_path)
    policies_path = release_dir / "policies.json"
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    policies["fault_policy"].pop("classification")
    _write_json(policies_path, policies)
    _refresh_release_hashes(release_dir)
    report_path = tmp_path / "verification_report.json"

    result, report = _run_verifier(release_dir, report_path)

    assert result.returncode != 0
    closure_check = _check(report, "policy_reference_closure")
    assert closure_check["passed"] is False
    assert any("fault_policy.classification" in error for error in closure_check["errors"])


def test_unknown_source_fallback_fault_class_fails_after_reseal(tmp_path: Path) -> None:
    release_dir = _copy_release(tmp_path)
    policies_path = release_dir / "policies.json"
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    policies["fault_policy"]["source_candidate_fallback_faults"].append("NOT_A_FAILURE_CLASS")
    _write_json(policies_path, policies)
    _refresh_release_hashes(release_dir)
    report_path = tmp_path / "verification_report.json"

    result, report = _run_verifier(release_dir, report_path)

    assert result.returncode != 0
    closure_check = _check(report, "policy_reference_closure")
    assert closure_check["passed"] is False
    assert any("NOT_A_FAILURE_CLASS" in error for error in closure_check["errors"])


def test_unknown_empty_coverage_source_fails_after_reseal(tmp_path: Path) -> None:
    release_dir = _copy_release(tmp_path)
    policies_path = release_dir / "policies.json"
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    policies["fault_policy"]["empty_coverage_status_by_source"] = {
        "raw.missing.source": "coverage_empty"
    }
    _write_json(policies_path, policies)
    _refresh_release_hashes(release_dir)
    report_path = tmp_path / "verification_report.json"

    result, report = _run_verifier(release_dir, report_path)

    assert result.returncode != 0
    closure_check = _check(report, "policy_reference_closure")
    assert closure_check["passed"] is False
    assert any("raw.missing.source" in error for error in closure_check["errors"])


def test_unauthorized_large_artifact_sampling_fails_after_reseal(tmp_path: Path) -> None:
    release_dir = _copy_release(tmp_path)
    policies_path = release_dir / "policies.json"
    policies = json.loads(policies_path.read_text(encoding="utf-8"))
    policies["artifact_evaluation_policy"]["large_artifact_mode"] = "sample"
    policies["artifact_evaluation_policy"]["sampling_policy"]["authorized"] = False
    _write_json(policies_path, policies)
    _refresh_release_hashes(release_dir)
    report_path = tmp_path / "verification_report.json"

    result, report = _run_verifier(release_dir, report_path)

    assert result.returncode != 0
    closure_check = _check(report, "policy_reference_closure")
    assert closure_check["passed"] is False
    assert any("sampling_policy.authorized" in error for error in closure_check["errors"])


def test_missing_release_directory_still_writes_failure_report(tmp_path: Path) -> None:
    report_path = tmp_path / "verification_report.json"

    result, report = _run_verifier(tmp_path / "missing-release", report_path)

    assert result.returncode != 0
    assert report["passed"] is False
    assert "release_status" in report["summary"]["failed_check_ids"]


def test_non_frozen_release_status_fails(tmp_path: Path) -> None:
    release_dir = _copy_release(tmp_path)
    release_path = release_dir / "release.json"
    release = json.loads(release_path.read_text(encoding="utf-8"))
    release["status"] = "draft"
    _write_json(release_path, release)
    report_path = tmp_path / "verification_report.json"

    result, report = _run_verifier(release_dir, report_path)

    assert result.returncode != 0
    status_check = _check(report, "release_status")
    assert status_check["passed"] is False
    assert any("frozen" in error for error in status_check["errors"])
