from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import geopandas as gpd
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


def test_evaluate_cases_includes_summary_metadata(tmp_path: Path, monkeypatch) -> None:
    case_a = tmp_path / "case_a"
    _write_case(case_a, case_id="case_a")

    monkeypatch.setattr(eval_harness, "_detect_git_commit_sha", lambda: "abc123")
    monkeypatch.setenv("GEOFUSION_KG_BACKEND", "memory")
    monkeypatch.setenv("GEOFUSION_LLM_PROVIDER", "mock")
    monkeypatch.setenv("GEOFUSION_CELERY_EAGER", "1")

    def fake_request_builder(case_dir: Path) -> dict:
        return {
            "case_id": case_dir.name,
            "expected_plan_checks": {},
            "artifact_checks": {},
        }

    def fake_runner(case_dir: Path, *, base_url: str, timeout_sec: float) -> dict:
        assert base_url == "http://unit.test"
        assert timeout_sec == 12.0
        return {"run_id": f"run-{case_dir.name}", "artifact_size": 123, "plan": {}, "artifact_entries": []}

    def fake_validator(result: dict, *, expected_plan_checks: dict, artifact_checks: dict) -> None:
        _ = result
        _ = expected_plan_checks
        _ = artifact_checks

    summary = eval_harness.evaluate_cases(
        case_dirs=[case_a],
        base_url="http://unit.test",
        timeout_sec=12.0,
        request_builder=fake_request_builder,
        runner=fake_runner,
        validator=fake_validator,
    )

    assert summary["command_mode"] == "golden-case"
    assert summary["base_url"] == "http://unit.test"
    assert summary["timeout_sec"] == 12.0
    assert summary["commit_sha"] == "abc123"
    assert summary["environment"] == {
        "kg_backend": "memory",
        "llm_provider": "mock",
        "celery_eager": "1",
    }


def test_evaluate_manifest_cases_skips_non_runnable_and_runs_agent_ready(monkeypatch) -> None:
    cases = [
        {
            "case_id": "building_ok",
            "execution_mode": "agent",
            "readiness": "agent-ready",
            "theme": "building",
            "timeout_sec": 90.0,
        },
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
        assert timeout_sec == 90.0
        return {
            "case_id": case["case_id"],
            "case_dir": None,
            "status": "passed",
            "duration_ms": 1,
            "run_id": "run-building_ok",
            "artifact_size": 10,
            "error": None,
            "timeout_sec": timeout_sec,
        }

    monkeypatch.setattr(eval_harness, "_preflight_manifest_api", lambda _base_url: None)
    monkeypatch.setattr(eval_harness, "_preflight_manifest_case_inputs", lambda _case: None)
    monkeypatch.setattr(eval_harness, "_evaluate_single_manifest_case", fake_eval)
    summary = eval_harness.evaluate_manifest_cases(cases=cases, base_url="http://unit.test", timeout_sec=12.0)

    assert called == ["building_ok"]
    assert summary["totals"] == {"total": 3, "passed": 1, "failed": 0, "skipped": 2}
    assert summary["cases"][1]["status"] == "skipped"
    assert "legacy-script" in str(summary["cases"][1]["error"])
    assert summary["cases"][2]["status"] == "skipped"
    assert "missing reference road source" in str(summary["cases"][2]["error"])
    assert summary["cases"][0]["timeout_sec"] == 90.0


def test_manifest_case_timeout_overrides_cli_default_only_for_that_case(monkeypatch) -> None:
    cases = [
        {"case_id": "case_default", "execution_mode": "agent", "readiness": "agent-ready", "theme": "building"},
        {
            "case_id": "case_override",
            "execution_mode": "agent",
            "readiness": "agent-ready",
            "theme": "building",
            "timeout_sec": 75.0,
        },
    ]
    seen: list[tuple[str, float]] = []

    def fake_eval(*, case: dict, base_url: str, timeout_sec: float, runner, validator) -> dict:
        _ = runner
        _ = validator
        _ = base_url
        seen.append((case["case_id"], timeout_sec))
        return {
            "case_id": case["case_id"],
            "case_dir": None,
            "status": "passed",
            "duration_ms": 1,
            "run_id": f"run-{case['case_id']}",
            "artifact_size": 10,
            "error": None,
            "timeout_sec": timeout_sec,
        }

    monkeypatch.setattr(eval_harness, "_preflight_manifest_api", lambda _base_url: None)
    monkeypatch.setattr(eval_harness, "_preflight_manifest_case_inputs", lambda _case: None)
    monkeypatch.setattr(eval_harness, "_evaluate_single_manifest_case", fake_eval)
    summary = eval_harness.evaluate_manifest_cases(cases=cases, base_url="http://unit.test", timeout_sec=12.0)

    assert seen == [("case_default", 12.0), ("case_override", 75.0)]
    assert [item["timeout_sec"] for item in summary["cases"]] == [12.0, 75.0]


def test_evaluate_manifest_cases_includes_summary_metadata(monkeypatch) -> None:
    monkeypatch.setattr(eval_harness, "_detect_git_commit_sha", lambda: "def456")
    monkeypatch.setenv("GEOFUSION_KG_BACKEND", "neo4j")
    monkeypatch.setenv("GEOFUSION_LLM_PROVIDER", "openai")
    monkeypatch.setenv("GEOFUSION_CELERY_EAGER", "0")

    def fake_eval(*, case: dict, base_url: str, timeout_sec: float, runner, validator) -> dict:
        _ = runner
        _ = validator
        return {
            "case_id": case["case_id"],
            "case_dir": None,
            "status": "passed",
            "duration_ms": 1,
            "run_id": "run-building_ok",
            "artifact_size": 10,
            "error": None,
            "timeout_sec": timeout_sec,
        }

    monkeypatch.setattr(eval_harness, "_preflight_manifest_api", lambda _base_url: None)
    monkeypatch.setattr(eval_harness, "_preflight_manifest_case_inputs", lambda _case: None)
    monkeypatch.setattr(eval_harness, "_evaluate_single_manifest_case", fake_eval)
    summary = eval_harness.evaluate_manifest_cases(
        cases=[{"case_id": "building_ok", "execution_mode": "agent", "readiness": "agent-ready", "theme": "building"}],
        base_url="http://manifest.test",
        timeout_sec=45.0,
    )

    assert summary["command_mode"] == "manifest"
    assert summary["base_url"] == "http://manifest.test"
    assert summary["timeout_sec"] == 45.0
    assert summary["commit_sha"] == "def456"
    assert summary["environment"] == {
        "kg_backend": "neo4j",
        "llm_provider": "openai",
        "celery_eager": "0",
    }


def test_evaluate_cases_uses_runtime_metadata_when_local_env_is_unset(tmp_path: Path, monkeypatch) -> None:
    case_a = tmp_path / "case_a"
    _write_case(case_a, case_id="case_a")

    monkeypatch.setattr(eval_harness, "_detect_git_commit_sha", lambda: "abc123")
    monkeypatch.delenv("GEOFUSION_KG_BACKEND", raising=False)
    monkeypatch.delenv("GEOFUSION_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GEOFUSION_CELERY_EAGER", raising=False)

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return (
                b'{"kg_backend":"neo4j","llm_provider":"mock","celery_eager":"0","api_port":"8010"}'
            )

    def fake_urlopen(request, timeout=0):
        assert request.full_url == "http://unit.test/api/v2/runtime"
        assert timeout == 5
        return _FakeResponse()

    monkeypatch.setattr(eval_harness.urllib.request, "urlopen", fake_urlopen)

    def fake_request_builder(case_dir: Path) -> dict:
        return {
            "case_id": case_dir.name,
            "expected_plan_checks": {},
            "artifact_checks": {},
        }

    def fake_runner(case_dir: Path, *, base_url: str, timeout_sec: float) -> dict:
        assert base_url == "http://unit.test"
        assert timeout_sec == 12.0
        return {"run_id": f"run-{case_dir.name}", "artifact_size": 123, "plan": {}, "artifact_entries": []}

    def fake_validator(result: dict, *, expected_plan_checks: dict, artifact_checks: dict) -> None:
        _ = result
        _ = expected_plan_checks
        _ = artifact_checks

    summary = eval_harness.evaluate_cases(
        case_dirs=[case_a],
        base_url="http://unit.test",
        timeout_sec=12.0,
        request_builder=fake_request_builder,
        runner=fake_runner,
        validator=fake_validator,
    )

    assert summary["environment"] == {
        "kg_backend": "neo4j",
        "llm_provider": "mock",
        "celery_eager": "0",
    }


def test_evaluate_manifest_cases_fails_fast_when_api_preflight_fails(monkeypatch) -> None:
    cases = [
        {"case_id": "building_ok", "execution_mode": "agent", "readiness": "agent-ready", "theme": "building"},
        {"case_id": "poi_script", "execution_mode": "legacy-script", "readiness": "script-ready", "theme": "poi"},
    ]

    monkeypatch.setattr(
        eval_harness,
        "_preflight_manifest_api",
        lambda _base_url: (_ for _ in ()).throw(RuntimeError("api unreachable")),
    )

    def fail_if_called(**_kwargs):
        raise AssertionError("runner path should not be reached when API preflight fails")

    monkeypatch.setattr(eval_harness, "_evaluate_single_manifest_case", fail_if_called)
    summary = eval_harness.evaluate_manifest_cases(cases=cases, base_url="http://unit.test", timeout_sec=12.0)

    assert summary["totals"] == {"total": 2, "passed": 0, "failed": 1, "skipped": 1}
    assert summary["cases"][0]["status"] == "failed"
    assert "api unreachable" in str(summary["cases"][0]["error"])
    assert summary["cases"][1]["status"] == "skipped"


def test_evaluate_manifest_cases_fails_fast_on_missing_input_before_runner(monkeypatch, tmp_path: Path) -> None:
    osm_shp = tmp_path / "src" / "osm_case.shp"
    _write_dummy_shapefile_bundle(osm_shp)

    monkeypatch.setattr(eval_harness, "_preflight_manifest_api", lambda _base_url: None)

    def fail_if_called(**_kwargs):
        raise AssertionError("runner path should not be reached when input preflight fails")

    monkeypatch.setattr(eval_harness, "_evaluate_single_manifest_case", fail_if_called)
    summary = eval_harness.evaluate_manifest_cases(
        cases=[
            {
                "case_id": "building_missing_ref",
                "execution_mode": "agent",
                "readiness": "agent-ready",
                "theme": "building",
                "inputs": {
                    "osm": str(osm_shp),
                    "reference": str(tmp_path / "src" / "missing_ref.shp"),
                },
            }
        ],
        base_url="http://unit.test",
        timeout_sec=12.0,
    )

    assert summary["totals"] == {"total": 1, "passed": 0, "failed": 1, "skipped": 0}
    assert summary["cases"][0]["status"] == "failed"
    assert "Manifest preflight reference shapefile not found" in str(summary["cases"][0]["error"])


def test_preflight_manifest_case_inputs_accepts_source_id_inputs(monkeypatch) -> None:
    class _StubSourceAssetService:
        def can_materialize(self, source_id: str) -> bool:
            return source_id in {"raw.osm.building", "raw.microsoft.building"}

    monkeypatch.setattr(eval_harness, "_build_source_asset_service", lambda: _StubSourceAssetService())

    eval_harness._preflight_manifest_case_inputs(
        {
            "case_id": "building_msft",
            "theme": "building",
            "inputs": {
                "osm_source_id": "raw.osm.building",
                "reference_source_id": "raw.microsoft.building",
            },
        }
    )


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


def test_materialize_manifest_case_supports_source_id_inputs(tmp_path: Path, monkeypatch) -> None:
    asset_dir = tmp_path / "assets"
    osm_shp = asset_dir / "osm.shp"
    ref_shp = asset_dir / "ref.shp"
    _write_dummy_shapefile_bundle(osm_shp)
    _write_dummy_shapefile_bundle(ref_shp)

    class _StubSourceAssetService:
        def resolve_raw_source_path(self, source_id: str, *, request_bbox=None):
            _ = request_bbox
            mapping = {
                "raw.osm.building": type("Resolution", (), {"path": osm_shp})(),
                "raw.microsoft.building": type("Resolution", (), {"path": ref_shp})(),
            }
            return mapping[source_id]

    monkeypatch.setattr(eval_harness, "_build_source_asset_service", lambda: _StubSourceAssetService())

    case_dir = eval_harness._materialize_manifest_case(
        {
            "case_id": "building_msft",
            "theme": "building",
            "execution_mode": "agent",
            "readiness": "agent-ready",
            "inputs": {
                "osm_source_id": "raw.osm.building",
                "reference_source_id": "raw.microsoft.building",
            },
        },
        tmp_path / "work",
    )

    assert (case_dir / "input" / "osm.zip").exists()
    assert (case_dir / "input" / "ref.zip").exists()


def test_materialize_manifest_case_clips_inputs_when_clip_bbox_is_provided(tmp_path: Path) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    osm_shp = src_dir / "osm_case.shp"
    ref_shp = src_dir / "ref_case.shp"
    geometry = gpd.GeoSeries.from_wkt(
        [
            "POLYGON ((0 0, 0 1, 1 1, 1 0, 0 0))",
            "POLYGON ((0.5 0.5, 0.5 1.5, 1.5 1.5, 1.5 0.5, 0.5 0.5))",
        ],
        crs="EPSG:4326",
    )
    gpd.GeoDataFrame({"name": ["a", "b"]}, geometry=geometry).to_file(osm_shp)
    gpd.GeoDataFrame({"name": ["r1", "r2"]}, geometry=geometry).to_file(ref_shp)

    case = {
        "case_id": "building_micro_case",
        "theme": "building",
        "execution_mode": "agent",
        "readiness": "agent-ready",
        "clip_bbox": [0.25, 0.25, 0.55, 0.55],
        "inputs": {
            "osm": str(osm_shp),
            "reference": str(ref_shp),
        },
    }

    case_dir = eval_harness._materialize_manifest_case(case, tmp_path / "work")
    payload = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))

    assert payload["trigger"]["spatial_extent"] == "bbox(0.25,0.25,0.55,0.55)"

    extract_dir = tmp_path / "extract"
    with ZipFile(case_dir / "input" / "osm.zip", "r") as zf:
        zf.extractall(extract_dir / "osm")
    with ZipFile(case_dir / "input" / "ref.zip", "r") as zf:
        zf.extractall(extract_dir / "ref")

    osm_out = gpd.read_file(next((extract_dir / "osm").glob("*.shp")))
    ref_out = gpd.read_file(next((extract_dir / "ref").glob("*.shp")))
    for frame in [osm_out, ref_out]:
        minx, miny, maxx, maxy = frame.to_crs("EPSG:4326").total_bounds.tolist()
        assert minx >= 0.25
        assert miny >= 0.25
        assert maxx <= 0.55
        assert maxy <= 0.55


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

    printed = json.loads(capsys.readouterr().out)
    assert printed["totals"]["total"] == 1


def test_main_supports_manifest_mode(tmp_path: Path, monkeypatch, capsys) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest(manifest_path, cases=[{"case_id": "alpha", "theme": "building"}])
    expected_summary = {
        "generated_at": "2026-01-01T00:00:00Z",
        "command_mode": "manifest",
        "base_url": "http://127.0.0.1:8000",
        "timeout_sec": 180.0,
        "commit_sha": "abc123",
        "environment": {"kg_backend": None, "llm_provider": None, "celery_eager": None},
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
                "timeout_sec": 1200.0,
            }
        ],
    }

    monkeypatch.setattr(eval_harness, "load_manifest_cases", lambda **_kwargs: [{"case_id": "alpha"}])
    monkeypatch.setattr(eval_harness, "evaluate_manifest_cases", lambda **_kwargs: dict(expected_summary))
    monkeypatch.setattr(eval_harness, "_detect_git_commit_sha", lambda: "abc123")

    code = eval_harness.main(["--manifest", str(manifest_path), "--case", "alpha"])

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["manifest"] == str(manifest_path.resolve())
    assert printed["selected_cases"] == ["alpha"]
