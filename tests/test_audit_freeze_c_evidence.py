from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.audit_freeze_c_evidence import audit_freeze_c, main, sha256_file
from scripts.run_contract_case_experiments import _assert_new_experiment_dir


def _make_bundle(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "evidence"
    paths = [
        root / "cases" / "C02" / "prepared_inputs_priority_delivery.json",
        root / "runtime" / "runs" / "run-1" / "input" / "request.json",
        root / "runtime" / "runs" / "run-1" / "output" / "artifact.json",
        root / "runtime" / "downloads" / "raw" / "source.bin",
    ]
    for index, path in enumerate(paths):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"file-{index}".encode("ascii"))

    external = tmp_path / "external-source.bin"
    external.write_bytes(b"external")
    manifest_path = root / "experiment_evidence_manifest.json"
    result_path = root / "experiment_result.json"
    result_path.write_text(
        json.dumps(
            {
                "experiment_id": "test-freeze-c",
                "all_cases_passed": True,
                "case_results": [{"case_id": "C02", "passed": True}],
                "evidence_manifest_path": str(manifest_path),
            }
        ),
        encoding="utf-8",
    )
    package_paths = paths + [result_path]
    manifest = {
        "experiment_id": "test-freeze-c",
        "output_dir": str(root),
        "commit_sha": "abc123",
        "seed_hash": "seed",
        "runtime_settings_hash": "settings",
        "metric_definition_hash": "metrics",
        "files": [
            {
                "relative_path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
                "size_bytes": path.stat().st_size,
            }
            for path in package_paths
        ],
        "external_inputs": [
            {
                "source_id": "raw.test.source",
                "product": "road",
                "original_path": str(external),
                "dataset_version": "v1",
                "observed_at": "2026-08-01T00:00:00+08:00",
                "freshness_status": "test",
                "semantic_status": "test",
                "files": [
                    {
                        "path": str(external),
                        "sha256": sha256_file(external),
                        "size_bytes": external.stat().st_size,
                    }
                ],
            }
        ],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return root, manifest_path, external


def _check(report: dict, check_id: str) -> dict:
    return next(item for item in report["checks"] if item["id"] == check_id)


def test_clean_freeze_c_bundle_passes_and_reports_hash_groups(tmp_path: Path) -> None:
    root, manifest_path, _ = _make_bundle(tmp_path)

    report = audit_freeze_c(
        evidence_dir=root,
        manifest_path=manifest_path,
        expected_commit="abc123",
        expected_manifest_sha256=sha256_file(manifest_path).upper(),
    )

    assert report["passed"] is True
    assert _check(report, "manifest_hash")["details"]["externally_anchored"] is True
    categories = _check(report, "package_hashes")["details"]["category_counts"]
    assert categories["prepared_input"] == 1
    assert categories["runtime_input"] == 1
    assert categories["runtime_output"] == 1
    assert categories["raw_package"] == 1


def test_external_input_tamper_fails(tmp_path: Path) -> None:
    root, manifest_path, external = _make_bundle(tmp_path)
    external.write_bytes(b"tampered")

    report = audit_freeze_c(evidence_dir=root, manifest_path=manifest_path)

    assert report["passed"] is False
    assert _check(report, "external_input_hashes")["passed"] is False


def test_output_tamper_fails(tmp_path: Path) -> None:
    root, manifest_path, _ = _make_bundle(tmp_path)
    output = root / "runtime" / "runs" / "run-1" / "output" / "artifact.json"
    output.write_bytes(b"tampered")

    report = audit_freeze_c(evidence_dir=root, manifest_path=manifest_path)

    assert report["passed"] is False
    assert _check(report, "package_hashes")["passed"] is False


def test_prepared_input_tamper_fails(tmp_path: Path) -> None:
    root, manifest_path, _ = _make_bundle(tmp_path)
    prepared = root / "cases" / "C02" / "prepared_inputs_priority_delivery.json"
    prepared.write_bytes(b"tampered")

    report = audit_freeze_c(evidence_dir=root, manifest_path=manifest_path)

    assert report["passed"] is False
    assert _check(report, "package_hashes")["passed"] is False


def test_manifest_tamper_fails_when_external_hash_is_pinned(tmp_path: Path) -> None:
    root, manifest_path, _ = _make_bundle(tmp_path)
    expected_hash = sha256_file(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["commit_sha"] = "changed"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    report = audit_freeze_c(
        evidence_dir=root,
        manifest_path=manifest_path,
        expected_manifest_sha256=expected_hash,
    )

    assert report["passed"] is False
    assert _check(report, "manifest_hash")["passed"] is False


def test_unexpected_package_file_fails_clean_check(tmp_path: Path) -> None:
    root, manifest_path, _ = _make_bundle(tmp_path)
    (root / "unexpected.txt").write_text("extra", encoding="utf-8")

    report = audit_freeze_c(evidence_dir=root, manifest_path=manifest_path)

    assert report["passed"] is False
    assert any("unexpected.txt" in error for error in _check(report, "package_hashes")["errors"])


def test_non_empty_experiment_dir_is_protected(tmp_path: Path) -> None:
    experiment_dir = tmp_path / "experiment"
    experiment_dir.mkdir()
    (experiment_dir / "old-evidence.json").write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError, match="非空"):
        _assert_new_experiment_dir(experiment_dir)


def test_all_cases_passed_false_returns_failed_audit(tmp_path: Path) -> None:
    root, manifest_path, _ = _make_bundle(tmp_path)
    result_path = root / "experiment_result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["all_cases_passed"] = False
    result_path.write_text(json.dumps(result), encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    item = next(item for item in manifest["files"] if item["relative_path"] == "experiment_result.json")
    item["sha256"] = hashlib.sha256(result_path.read_bytes()).hexdigest()
    item["size_bytes"] = result_path.stat().st_size
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    report = audit_freeze_c(evidence_dir=root, manifest_path=manifest_path)

    assert report["passed"] is False
    assert _check(report, "experiment_result")["passed"] is False
    assert (
        main(
            [
                "--evidence-dir",
                str(root),
                "--manifest",
                str(manifest_path),
                "--report-json",
                str(tmp_path / "audit.json"),
                "--summary-markdown",
                str(tmp_path / "audit.md"),
            ]
        )
        == 1
    )
