from __future__ import annotations

import io
import zipfile
from pathlib import Path

import urllib.request

from utils import local_smoke
from utils.local_smoke import build_run_request_from_case, validate_smoke_result


def test_build_run_request_from_case_reads_golden_case_manifest(tmp_path: Path) -> None:
    case_dir = tmp_path / "building_disaster_flood"
    input_dir = case_dir / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "osm.zip").write_bytes(b"osm")
    (input_dir / "ref.zip").write_bytes(b"ref")
    (case_dir / "case.json").write_text(
        """
        {
          "case_id": "building_disaster_flood",
          "job_type": "building",
          "trigger": {
            "type": "disaster_event",
            "content": "flood building fusion",
            "disaster_type": "flood"
          },
          "osm_zip": "input/osm.zip",
          "ref_zip": "input/ref.zip"
        }
        """,
        encoding="utf-8",
    )

    payload = build_run_request_from_case(case_dir)

    assert payload["form"]["job_type"] == "building"
    assert payload["form"]["trigger_type"] == "disaster_event"
    assert payload["form"]["trigger_content"] == "flood building fusion"
    assert payload["form"]["disaster_type"] == "flood"
    assert payload["osm_zip_path"] == input_dir / "osm.zip"
    assert payload["ref_zip_path"] == input_dir / "ref.zip"


def test_validate_smoke_result_checks_plan_and_artifact_expectations() -> None:
    result = {
        "plan": {
            "context": {
                "retrieval": {
                    "candidate_patterns": [{"pattern_id": "wp.flood.building.default"}],
                    "algorithms": {
                        "algo.fusion.building.v1": {"algo_id": "algo.fusion.building.v1"},
                        "algo.fusion.building.safe": {"algo_id": "algo.fusion.building.safe"},
                    },
                }
            },
            "tasks": [
                {"algorithm_id": "algo.fusion.building.v1", "alternatives": ["algo.fusion.building.safe"]},
            ],
            "expected_output": "dt.building.fused",
        },
        "artifact_entries": ["result.shp", "result.shx", "result.dbf"],
    }

    validate_smoke_result(
        result,
        expected_plan_checks={
            "pattern_hint": "wp.flood.building.default",
            "required_algorithms": ["algo.fusion.building.v1", "algo.fusion.building.safe"],
            "required_output_type": "dt.building.fused",
        },
        artifact_checks={"required_suffixes": [".shp", ".shx", ".dbf"]},
    )


def test_run_local_v2_smoke_uses_case_timeout_for_http_requests(tmp_path: Path, monkeypatch) -> None:
    case_dir = tmp_path / "building_real"
    input_dir = case_dir / "input"
    input_dir.mkdir(parents=True)
    (input_dir / "osm.zip").write_bytes(b"osm")
    (input_dir / "ref.zip").write_bytes(b"ref")
    (case_dir / "case.json").write_text(
        """
        {
          "case_id": "building_real",
          "job_type": "building",
          "trigger": {
            "type": "disaster_event",
            "content": "real building fusion",
            "disaster_type": "flood"
          },
          "osm_zip": "input/osm.zip",
          "ref_zip": "input/ref.zip"
        }
        """,
        encoding="utf-8",
    )

    artifact_buf = io.BytesIO()
    with zipfile.ZipFile(artifact_buf, "w") as zf:
        zf.writestr("result.shp", b"shape")
        zf.writestr("result.shx", b"index")
        zf.writestr("result.dbf", b"table")
    artifact_bytes = artifact_buf.getvalue()

    monkeypatch.setattr(local_smoke.time, "time", lambda: 100.0)
    monkeypatch.setattr(local_smoke.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(local_smoke, "_encode_multipart", lambda _form, _files: (b"body", "boundary"))

    http_calls: list[tuple[str, str, float]] = []

    def fake_json_request(method: str, url: str, *, data=None, headers=None, timeout_sec: float = 30.0):
        _ = data
        _ = headers
        http_calls.append((method, url, timeout_sec))
        if method == "POST":
            return {"run_id": "run-123"}
        if url.endswith("/plan"):
            return {"plan": {"tasks": [], "context": {"retrieval": {"candidate_patterns": [], "algorithms": {}}}}}
        return {"phase": "succeeded"}

    monkeypatch.setattr(local_smoke, "_json_request", fake_json_request)

    artifact_timeouts: list[float] = []

    class _FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return artifact_bytes

    def fake_urlopen(request: urllib.request.Request, timeout: float = 30.0):
        artifact_timeouts.append(timeout)
        assert request.full_url.endswith("/artifact")
        return _FakeResponse()

    monkeypatch.setattr(local_smoke.urllib.request, "urlopen", fake_urlopen)

    result = local_smoke.run_local_v2_smoke(case_dir, base_url="http://unit.test", timeout_sec=123.0)

    assert result["run_id"] == "run-123"
    assert [timeout for _, _, timeout in http_calls] == [123.0, 123.0, 123.0]
    assert artifact_timeouts == [123.0]
