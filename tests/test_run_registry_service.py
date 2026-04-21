import os
from pathlib import Path

from services.run_registry_service import RunRegistryService


def test_run_registry_lists_persisted_run_json(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-a"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(
        '{"run_id":"run-a","phase":"succeeded","job_type":"building"}',
        encoding="utf-8",
    )

    records = RunRegistryService(runs_root=tmp_path / "runs").list_records(limit=10)

    assert records[0]["run_id"] == "run-a"
    assert records[0]["phase"] == "succeeded"
    assert records[0]["job_type"] == "building"


def test_run_registry_filters_and_sorts_by_run_json_mtime(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    older = runs_root / "run-old"
    newer = runs_root / "run-new"
    skipped = runs_root / "run-skipped"
    for run_dir in [older, newer, skipped]:
        run_dir.mkdir(parents=True)

    (older / "run.json").write_text(
        '{"run_id":"run-old","phase":"succeeded","job_type":"building"}',
        encoding="utf-8",
    )
    (newer / "run.json").write_text(
        '{"run_id":"run-new","phase":"succeeded","job_type":"building"}',
        encoding="utf-8",
    )
    (skipped / "run.json").write_text(
        '{"run_id":"run-skipped","phase":"failed","job_type":"water"}',
        encoding="utf-8",
    )

    older_time = 1_700_000_000
    newer_time = 1_700_000_100
    skipped_time = 1_700_000_200
    (older / "run.json").touch()
    (newer / "run.json").touch()
    (skipped / "run.json").touch()

    os.utime(older / "run.json", (older_time, older_time))
    os.utime(newer / "run.json", (newer_time, newer_time))
    os.utime(skipped / "run.json", (skipped_time, skipped_time))

    records = RunRegistryService(runs_root=runs_root).list_records(
        limit=10,
        phase="succeeded",
        job_type="building",
    )

    assert [record["run_id"] for record in records] == ["run-new", "run-old"]
    assert records[0]["run_dir"] == str(newer)


def test_run_registry_skips_malformed_and_non_object_run_json(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    valid = runs_root / "run-valid"
    malformed = runs_root / "run-malformed"
    array_payload = runs_root / "run-array"
    string_payload = runs_root / "run-string"
    for run_dir in [valid, malformed, array_payload, string_payload]:
        run_dir.mkdir(parents=True)

    (valid / "run.json").write_text(
        '{"run_id":"run-valid","phase":"succeeded","job_type":"building"}',
        encoding="utf-8",
    )
    (malformed / "run.json").write_text('{"run_id":', encoding="utf-8")
    (array_payload / "run.json").write_text('["run-array"]', encoding="utf-8")
    (string_payload / "run.json").write_text('"run-string"', encoding="utf-8")

    records = RunRegistryService(runs_root=runs_root).list_records(limit=10)

    assert [record["run_id"] for record in records] == ["run-valid"]


def test_run_registry_caps_limit_at_100(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    for index in range(105):
        run_dir = runs_root / f"run-{index:03d}"
        run_dir.mkdir(parents=True)
        (run_dir / "run.json").write_text(
            f'{{"run_id":"run-{index:03d}","phase":"succeeded","job_type":"building"}}',
            encoding="utf-8",
        )

    records = RunRegistryService(runs_root=runs_root).list_records(limit=500)

    assert len(records) == 100
