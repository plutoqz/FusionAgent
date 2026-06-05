import json
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from services.validation_session_read_model_service import ValidationSessionReadModelService


def _summary_payload(
    root: Path,
    *,
    session_id: str,
    passed_cases: int = 1,
    failed_cases: int = 1,
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "matrix_path": "docs/superpowers/validation/engineering_validation_matrix.yaml",
        "total_cases": passed_cases + failed_cases,
        "passed_cases": passed_cases,
        "failed_cases": failed_cases,
        "output_root": str(root),
        "metadata": {"track": "D2"},
        "results": [
            {
                "case_id": f"{session_id}-ok",
                "passed": True,
                "phase": "succeeded",
                "scenario_id": "scenario-ok",
                "output_dir": str(root / session_id / "cases" / "ok"),
                "summary_path": str(root / session_id / "cases" / "ok" / "summary.json"),
                "failure_reasons": [],
                "observed": {"child_run_ids": ["run-ok"]},
            },
            {
                "case_id": f"{session_id}-failed",
                "passed": False,
                "phase": "partial",
                "scenario_id": "scenario-failed",
                "output_dir": str(root / session_id / "cases" / "failed"),
                "summary_path": str(root / session_id / "cases" / "failed" / "summary.json"),
                "failure_reasons": ["quality gate failed"],
                "observed": {"child_run_ids": ["run-failed"]},
                "error": "failed",
            },
        ],
    }


def _manifest_payload(
    root: Path,
    session_dir: Path,
    *,
    session_id: str,
    summary_path: str | None,
    created_at: str = "2026-06-05T08:00:00+00:00",
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "matrix_path": "docs/superpowers/validation/engineering_validation_matrix.yaml",
        "output_root": str(root),
        "summary_path": summary_path,
        "markdown_summary_path": str(session_dir / "validation_summary.md"),
        "created_at": created_at,
        "git_commit": "abc1234",
        "runtime": {"provider": "mock"},
    }


def _write_session(
    root: Path,
    *,
    session_id: str,
    created_at: str = "2026-06-05T08:00:00+00:00",
    passed_cases: int = 1,
    failed_cases: int = 1,
) -> Path:
    session_dir = root / session_id
    session_dir.mkdir(parents=True)
    summary_path = session_dir / "validation_summary.json"
    manifest = _manifest_payload(
        root,
        session_dir,
        session_id=session_id,
        summary_path=str(summary_path),
        created_at=created_at,
    )
    summary = _summary_payload(root, session_id=session_id, passed_cases=passed_cases, failed_cases=failed_cases)
    (session_dir / "validation_session.json").write_text(json.dumps(manifest), encoding="utf-8")
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    return session_dir


def test_validation_session_read_model_pairs_manifest_with_summary(tmp_path: Path) -> None:
    _write_session(tmp_path, session_id="session-new", created_at="2026-06-05T09:00:00+00:00")
    _write_session(tmp_path, session_id="session-old", created_at="2026-06-05T08:00:00+00:00")
    orphan_dir = tmp_path / "orphan"
    orphan_dir.mkdir()
    (orphan_dir / "validation_session.json").write_text(
        json.dumps(
            {
                "session_id": "orphan",
                "matrix_path": "matrix.yaml",
                "output_root": str(tmp_path),
            }
        ),
        encoding="utf-8",
    )

    records = ValidationSessionReadModelService(output_root=tmp_path).list_sessions()

    assert [record["session_id"] for record in records] == ["session-new", "session-old"]
    assert records[0]["created_at"] == "2026-06-05T09:00:00+00:00"
    assert records[0]["summary"]["failed_cases"] == 1
    assert records[0]["summary"]["results"][1]["failure_reasons"] == ["quality gate failed"]
    assert records[0]["git_commit"] == "abc1234"


def test_validation_sessions_api_uses_configured_output_root(tmp_path: Path, monkeypatch) -> None:
    _write_session(tmp_path, session_id="session-api")
    monkeypatch.setenv("GEOFUSION_VALIDATION_OUTPUT_ROOT", str(tmp_path))

    response = TestClient(create_app()).get("/api/v2/validation/sessions")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["records"][0]["session_id"] == "session-api"
    assert payload["records"][0]["summary"]["total_cases"] == 2


def test_validation_read_model_rejects_relative_summary_path_traversal(tmp_path: Path) -> None:
    root = tmp_path / "validation-root"
    session_dir = root / "session-traversal"
    outside_dir = tmp_path / "outside"
    session_dir.mkdir(parents=True)
    outside_dir.mkdir()
    outside_summary = outside_dir / "validation_summary.json"
    outside_summary.write_text(
        json.dumps(_summary_payload(root, session_id="session-traversal")),
        encoding="utf-8",
    )
    (session_dir / "validation_session.json").write_text(
        json.dumps(
            _manifest_payload(
                root,
                session_dir,
                session_id="session-traversal",
                summary_path="../../outside/validation_summary.json",
            )
        ),
        encoding="utf-8",
    )

    records = ValidationSessionReadModelService(output_root=root).list_sessions()

    assert records == []


def test_validation_read_model_rejects_absolute_summary_path_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "validation-root"
    session_dir = root / "session-absolute"
    outside_dir = tmp_path / "outside"
    session_dir.mkdir(parents=True)
    outside_dir.mkdir()
    outside_summary = outside_dir / "validation_summary.json"
    outside_summary.write_text(
        json.dumps(_summary_payload(root, session_id="session-absolute")),
        encoding="utf-8",
    )
    (session_dir / "validation_session.json").write_text(
        json.dumps(
            _manifest_payload(
                root,
                session_dir,
                session_id="session-absolute",
                summary_path=str(outside_summary),
            )
        ),
        encoding="utf-8",
    )

    records = ValidationSessionReadModelService(output_root=root).list_sessions()

    assert records == []


def test_validation_read_model_accepts_relative_summary_path_inside_session_dir(tmp_path: Path) -> None:
    root = tmp_path / "validation-root"
    session_dir = root / "session-relative"
    summary_dir = session_dir / "nested"
    summary_dir.mkdir(parents=True)
    (summary_dir / "validation_summary.json").write_text(
        json.dumps(_summary_payload(root, session_id="session-relative")),
        encoding="utf-8",
    )
    (session_dir / "validation_session.json").write_text(
        json.dumps(
            _manifest_payload(
                root,
                session_dir,
                session_id="session-relative",
                summary_path="nested/validation_summary.json",
            )
        ),
        encoding="utf-8",
    )

    records = ValidationSessionReadModelService(output_root=root).list_sessions()

    assert [record["session_id"] for record in records] == ["session-relative"]
    assert Path(records[0]["summary_path"]).resolve() == (summary_dir / "validation_summary.json").resolve()


def test_validation_read_model_rejects_summary_from_different_session_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "validation-root"
    session_dir = root / "session-a"
    other_session_dir = root / "session-b"
    session_dir.mkdir(parents=True)
    other_session_dir.mkdir()
    other_summary_path = other_session_dir / "validation_summary.json"
    other_summary_path.write_text(
        json.dumps(_summary_payload(root, session_id="session-b")),
        encoding="utf-8",
    )
    (session_dir / "validation_session.json").write_text(
        json.dumps(
            _manifest_payload(
                root,
                session_dir,
                session_id="session-a",
                summary_path=str(other_summary_path),
            )
        ),
        encoding="utf-8",
    )

    records = ValidationSessionReadModelService(output_root=root).list_sessions()

    assert records == []


def test_validation_read_model_skips_bad_manifest_bad_summary_and_missing_summary(tmp_path: Path) -> None:
    root = tmp_path / "validation-root"
    bad_manifest_dir = root / "bad-manifest"
    bad_summary_dir = root / "bad-summary"
    missing_summary_dir = root / "missing-summary"
    bad_manifest_dir.mkdir(parents=True)
    bad_summary_dir.mkdir()
    missing_summary_dir.mkdir()

    (bad_manifest_dir / "validation_session.json").write_text("{not-json", encoding="utf-8")
    (bad_summary_dir / "validation_session.json").write_text(
        json.dumps(
            _manifest_payload(
                root,
                bad_summary_dir,
                session_id="bad-summary",
                summary_path="validation_summary.json",
            )
        ),
        encoding="utf-8",
    )
    (bad_summary_dir / "validation_summary.json").write_text("{not-json", encoding="utf-8")
    (missing_summary_dir / "validation_session.json").write_text(
        json.dumps(
            _manifest_payload(
                root,
                missing_summary_dir,
                session_id="missing-summary",
                summary_path="validation_summary.json",
            )
        ),
        encoding="utf-8",
    )

    records = ValidationSessionReadModelService(output_root=root).list_sessions()

    assert records == []


def test_validation_sessions_api_uses_validation_specific_response_schema(tmp_path: Path, monkeypatch) -> None:
    _write_session(tmp_path, session_id="session-schema")
    monkeypatch.setenv("GEOFUSION_VALIDATION_OUTPUT_ROOT", str(tmp_path))

    client = TestClient(create_app())
    response = client.get("/api/v2/validation/sessions")
    openapi = client.get("/openapi.json").json()

    assert response.status_code == 200, response.text
    assert set(response.json()["records"][0]) >= {
        "session_id",
        "created_at",
        "git_commit",
        "matrix_path",
        "output_dir",
        "summary",
    }
    schema = openapi["paths"]["/api/v2/validation/sessions"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    assert schema["$ref"].endswith("/ValidationSessionListResponse")
