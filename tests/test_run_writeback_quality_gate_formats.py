from pathlib import Path

import pytest

from schemas.agent import RunCreateRequest, RunTrigger, RunTriggerType, WorkflowPlan
from schemas.fusion import JobType
from services.run_writeback_service import RunWritebackService


class _Coordinator:
    def __init__(self) -> None:
        self.registered = []

    def get_run(self, _run_id):
        return None

    def _validate_output_artifact_against_schema_policy(self, **_kwargs) -> None:
        return None

    def _zip_output_artifact(self, _artifact_path: Path, output_zip: Path) -> Path:
        output_zip.write_bytes(b"test-zip")
        return output_zip

    def _record_feedback(self, **_kwargs) -> None:
        return None

    def _register_artifact(self, **kwargs) -> None:
        self.registered.append(kwargs["artifact"])


@pytest.mark.parametrize("suffix", [".gpkg", ".shp", ".geojson"])
def test_writeback_routes_every_kg_supported_vector_format_through_quality_gate(
    tmp_path: Path,
    monkeypatch,
    suffix: str,
) -> None:
    coordinator = _Coordinator()
    service = RunWritebackService(coordinator)
    evaluated: list[Path] = []

    def fake_evaluate(**kwargs) -> Path:
        path = Path(kwargs["fused_shp"])
        evaluated.append(path)
        return path

    monkeypatch.setattr(service, "_evaluate_quality_and_repair_if_needed", fake_evaluate)
    artifact_path = tmp_path / f"fused{suffix}"
    artifact_path.write_bytes(b"vector")
    output_dir = tmp_path / f"output-{suffix.removeprefix('.')}"
    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        target_crs="EPSG:4326",
        field_mapping={},
        debug=False,
    )
    plan = WorkflowPlan(
        workflow_id="wf-quality-format",
        trigger=request.trigger,
        tasks=[],
        expected_output="building",
    )

    result = service.run_writeback_stage(
        run_id="run-quality-format",
        request=request,
        plan=plan,
        fused_shp=artifact_path,
        repair_records=[],
        output_dir=output_dir,
    )

    assert evaluated == [artifact_path]
    assert Path(result.path).is_file()
