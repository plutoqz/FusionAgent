from __future__ import annotations

import json
from pathlib import Path

import sys


_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts import eval_harness


def _write_case(case_dir: Path, *, case_id: str) -> None:
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / "case.json").write_text(
        json.dumps(
            {
                "case_id": case_id,
                "job_type": "building",
                "trigger": {
                    "type": "user_query",
                    "content": "fuse",
                },
                "osm_zip": "input/osm.zip",
                "ref_zip": "input/ref.zip",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _write_manifest(path: Path, *, cases: list[dict]) -> None:
    path.write_text(json.dumps({"version": "test", "cases": cases}, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_dummy_shapefile_bundle(shp_path: Path) -> None:
    shp_path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in [".shp", ".shx", ".dbf"]:
        shp_path.with_suffix(suffix).write_bytes(b"dummy")


def test_discover_case_dirs_supports_case_id_and_dir_name_filters(tmp_path: Path) -> None:
    root = tmp_path / "golden_cases"
    _write_case(root / "case_dir_a", case_id="alpha")
    _write_case(root / "case_dir_b", case_id="beta")

    all_cases = eval_harness.discover_case_dirs(root)
    assert [path.name for path in all_cases] == ["case_dir_a", "case_dir_b"]

    only_alpha = eval_harness.discover_case_dirs(root, selected_cases=["alpha"])
    assert [path.name for path in only_alpha] == ["case_dir_a"]

    only_dir_name = eval_harness.discover_case_dirs(root, selected_cases=["case_dir_b"])
    assert [path.name for path in only_dir_name] == ["case_dir_b"]


def test_load_manifest_cases_filters_by_case_id(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(
        manifest_path,
        cases=[
            {"case_id": "alpha", "theme": "building"},
            {"case_id": "beta", "theme": "road"},
        ],
    )

    all_cases = eval_harness.load_manifest_cases(manifest_path)
    assert [case["case_id"] for case in all_cases] == ["alpha", "beta"]

    only_beta = eval_harness.load_manifest_cases(manifest_path, selected_cases=["beta"])
    assert [case["case_id"] for case in only_beta] == ["beta"]


def test_evaluate_cases_keeps_going_after_failures(tmp_path: Path) -> None:
    case_a = tmp_path / "case_a"
    case_b = tmp_path / "case_b"
    _write_case(case_a, case_id="case_a")
    _write_case(case_b, case_id="case_b")

    def fake_request_builder(case_dir: Path) -> dict:
        return {
            "case_id": case_dir.name,
            "expected_plan_checks": {},
            "artifact_checks": {},
        }

    def fake_runner(case_dir: Path, *, base_url: str, timeout_sec: float) -> dict:
        assert base_url == "http://unit.test"
        assert timeout_sec == 12.0
        if case_dir.name == "case_b":
            raise RuntimeError("runner failed")
        return {"run_id": f"run-{case_dir.name}", "artifact_size": 123, "plan": {}, "artifact_entries": []}

    def fake_validator(result: dict, *, expected_plan_checks: dict, artifact_checks: dict) -> None:
        _ = expected_plan_checks
        _ = artifact_checks
        if result["run_id"] == "run-case_a":
            return
        raise AssertionError("unexpected")

    summary = eval_harness.evaluate_cases(
        case_dirs=[case_a, case_b],
        base_url="http://unit.test",
        timeout_sec=12.0,
        request_builder=fake_request_builder,
        runner=fake_runner,
        validator=fake_validator,
    )

    assert summary["totals"] == {"total": 2, "passed": 1, "failed": 1, "skipped": 0}
    assert summary["all_passed"] is False
    assert [item["case_id"] for item in summary["cases"]] == ["case_a", "case_b"]
    assert summary["cases"][0]["status"] == "passed"
    assert summary["cases"][1]["status"] == "failed"
    assert "RuntimeError: runner failed" in str(summary["cases"][1]["error"])


def test_evaluate_manifest_cases_skips_non_runnable_and_runs_agent_ready(monkeypatch) -> None:
    cases = [
        {"case_id": "building_ok", "execution_mode": "agent", "readiness": "agent-ready", "theme": "building"},
        {"case_id": "poi_script", "execution_mode": "legacy-script", "readiness": "script-ready", "theme": "poi"},
        {
            "case_id": "road_blocked",
            "execution_mode": "agent",
            "readiness": "blocked",
            "theme": "road",
            "blockers": ["missing reference road source"],
        },
    ]
    called: list[str] = []

    def fake_eval(*, case: dict, base_url: str, timeout_sec: float, runner, validator) -> dict:
        _ = runner
        _ = validator
        called.append(case["case_id"])
        assert base_url == "http://unit.test"
        assert timeout_sec == 12.0
        return {
            "case_id": case["case_id"],
            "case_dir": None,
            "status": "passed",
            "duration_ms": 1,
            "run_id": "run-building_ok",
            "artifact_size": 10,
            "error": None,
        }

    monkeypatch.setattr(eval_harness, "_evaluate_single_manifest_case", fake_eval)
    summary = eval_harness.evaluate_manifest_cases(cases=cases, base_url="http://unit.test", timeout_sec=12.0)

    assert called == ["building_ok"]
    assert summary["totals"] == {"total": 3, "passed": 1, "failed": 0, "skipped": 2}
    assert summary["cases"][1]["status"] == "skipped"
    assert "legacy-script" in str(summary["cases"][1]["error"])
    assert summary["cases"][2]["status"] == "skipped"
    assert "missing reference road source" in str(summary["cases"][2]["error"])


def test_materialize_manifest_case_creates_case_bundle(tmp_path: Path) -> None:
    osm_shp = tmp_path / "src" / "osm_case.shp"
    ref_shp = tmp_path / "src" / "ref_case.shp"
    _write_dummy_shapefile_bundle(osm_shp)
    _write_dummy_shapefile_bundle(ref_shp)

    case = {
        "case_id": "building_case",
        "theme": "building",
        "execution_mode": "agent",
        "readiness": "agent-ready",
        "inputs": {
            "osm": str(osm_shp),
            "reference": str(ref_shp),
        },
    }

    case_dir = eval_harness._materialize_manifest_case(case, tmp_path / "work")
    payload = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))

    assert payload["case_id"] == "building_case"
    assert payload["job_type"] == "building"
    assert (case_dir / "input" / "osm.zip").exists()
    assert (case_dir / "input" / "ref.zip").exists()
    assert "algo.fusion.building.v1" in payload["expected_plan_checks"]["required_algorithms"]


def test_main_writes_summary_json_and_exit_code_on_failure(tmp_path: Path, monkeypatch, capsys) -> None:
    expected_summary = {
        "generated_at": "2026-01-01T00:00:00Z",
        "totals": {"total": 1, "passed": 0, "failed": 1, "skipped": 0},
        "all_passed": False,
        "cases": [
            {
                "case_id": "broken",
                "case_dir": str(tmp_path / "broken"),
                "status": "failed",
                "duration_ms": 7,
                "run_id": None,
                "artifact_size": None,
                "error": "RuntimeError: boom",
            }
        ],
    }

    monkeypatch.setattr(eval_harness, "discover_case_dirs", lambda **_kwargs: [tmp_path / "broken"])
    monkeypatch.setattr(eval_harness, "evaluate_cases", lambda **_kwargs: dict(expected_summary))

    output_path = tmp_path / "out" / "summary.json"
    code = eval_harness.main(
        [
            "--cases-root",
            str(tmp_path),
            "--base-url",
            "http://unit.test",
            "--timeout",
            "5",
            "--output-json",
            str(output_path),
        ]
    )

    assert code == 1
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["totals"]["failed"] == 1
    assert saved["cases_root"] == str(tmp_path.resolve())

    stdout = capsys.readouterr().out
    printed = json.loads(stdout)
    assert printed["totals"]["total"] == 1


def test_main_supports_manifest_mode(tmp_path: Path, monkeypatch, capsys) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, cases=[{"case_id": "alpha", "theme": "building"}])
    expected_summary = {
        "generated_at": "2026-01-01T00:00:00Z",
        "totals": {"total": 1, "passed": 1, "failed": 0, "skipped": 0},
        "all_passed": True,
        "cases": [
            {
                "case_id": "alpha",
                "case_dir": None,
                "status": "passed",
                "duration_ms": 4,
                "run_id": "run-alpha",
                "artifact_size": 11,
                "error": None,
            }
        ],
    }

    monkeypatch.setattr(eval_harness, "load_manifest_cases", lambda **_kwargs: [{"case_id": "alpha"}])
    monkeypatch.setattr(eval_harness, "evaluate_manifest_cases", lambda **_kwargs: dict(expected_summary))

    code = eval_harness.main(["--manifest", str(manifest_path), "--case", "alpha"])

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["manifest"] == str(manifest_path.resolve())
    assert printed["selected_cases"] == ["alpha"]
