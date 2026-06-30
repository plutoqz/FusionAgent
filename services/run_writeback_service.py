from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from schemas.agent import RepairRecord, RunArtifactMeta, RunCreateRequest, RunPhase, WorkflowPlan
from services.output_contract_service import get_domain_output_contract
from schemas.task_kind import TaskKind, expand_job_type_to_task_kinds


class RunWritebackService:
    def __init__(self, coordinator: Any) -> None:
        self.coordinator = coordinator

    def run_writeback_stage(
        self,
        *,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        fused_shp: Path,
        repair_records: list[RepairRecord],
        output_dir: Path,
    ) -> RunArtifactMeta:
        service = self.coordinator
        output_dir.mkdir(parents=True, exist_ok=True)
        component_coverage = _component_coverage_from_status(service.get_run(run_id))
        service._validate_output_artifact_against_schema_policy(
            run_id=run_id,
            request=request,
            plan=plan,
            fused_shp=fused_shp,
        )
        if Path(fused_shp).suffix.lower() == ".gpkg":
            fused_shp = self._evaluate_quality_and_repair_if_needed(
                run_id=run_id,
                request=request,
                plan=plan,
                fused_shp=fused_shp,
                repair_records=repair_records,
                output_dir=output_dir,
                component_coverage=component_coverage,
            )
        artifact_zip = service._zip_output_artifact(
            fused_shp,
            output_dir / f"{request.job_type.value}_fusion_result.zip",
        )
        artifact = RunArtifactMeta(
            filename=artifact_zip.name,
            path=str(artifact_zip),
            size_bytes=artifact_zip.stat().st_size,
        )
        service._record_feedback(
            run_id=run_id,
            request=request,
            plan=plan,
            repair_records=repair_records,
            success=True,
            failure_reason=None,
        )
        service._register_artifact(run_id=run_id, request=request, plan=plan, artifact=artifact, repair_records=repair_records)
        return artifact

    def _evaluate_quality_and_repair_if_needed(
        self,
        *,
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        fused_shp: Path,
        repair_records: list[RepairRecord],
        output_dir: Path,
        component_coverage: dict[str, object],
    ) -> Path:
        service = self.coordinator
        contract_id = service._quality_contract_id_for_request(request)
        source_artifact_paths = _source_artifact_paths_from_component_coverage(component_coverage)
        task_kind = _task_kind_for_request(request)
        required_fields = service._quality_gate_required_fields_for_plan(plan, contract_id=contract_id)
        repair_required_fields = _merge_required_fields(
            required_fields,
            get_domain_output_contract(task_kind).required_fields,
        )
        requested_bbox = service._parse_bbox(request.trigger.spatial_extent)
        degradation_context = service._degradation_context_from_component_coverage(component_coverage)
        quality_policy_id = service._quality_policy_id_for_plan(plan)
        source_expected_null_rates = service._source_expected_null_rates_for_request(request, plan)
        quality_report = service.quality_gate_service.evaluate(
            artifact_path=fused_shp,
            task_kind=task_kind,
            required_fields=required_fields,
            requested_bbox=requested_bbox,
            component_coverage=component_coverage,
            source_artifact_paths=source_artifact_paths,
            degradation_context=degradation_context,
            quality_policy_id=quality_policy_id,
            contract_id=contract_id,
            source_expected_null_rates=source_expected_null_rates,
        )
        quality_report_path = output_dir / "quality_report.json"
        feature_alignment_path = output_dir / "feature_alignment_report.json"
        service._update_status(
            run_id,
            RunPhase.running,
            progress=92,
            plan_revision=service._extract_plan_revision(plan),
            checkpoint=service._checkpoint(stage="quality_gate", plan_revision=service._extract_plan_revision(plan)),
            event_kind="quality_gate_evaluated",
            event_message="Fusion output evaluated by quality gate.",
            event_details={
                "accepted": quality_report.accepted,
                "policy_id": quality_report.policy_id,
                "path": str(quality_report_path),
                "feature_alignment_path": str(feature_alignment_path),
                "failure_reasons": quality_report.failure_reasons,
                "policy_adaptations": quality_report.policy_adaptations,
            },
        )
        if not quality_report.accepted:
            before_repair_path = output_dir / "quality_report.before_repair.json"
            before_repair_path.write_text(
                json.dumps(quality_report.model_dump(mode="json"), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            service._update_status(
                run_id,
                RunPhase.running,
                progress=93,
                repair_records=repair_records,
                attempt_no=service._max_attempt_no(repair_records),
                healing_summary=service._build_healing_summary(repair_records),
                plan_revision=service._extract_plan_revision(plan),
                checkpoint=service._checkpoint(stage="artifact_repair", plan_revision=service._extract_plan_revision(plan)),
                event_kind="artifact_repair_started",
                event_message="Quality gate rejected output; artifact repair started.",
                event_details={
                    "input_path": str(fused_shp),
                    "quality_report_path": str(before_repair_path),
                    "failure_reasons": quality_report.failure_reasons,
                },
            )
            repair_result = service.artifact_repair_service.repair(
                artifact_path=fused_shp,
                task_kind=task_kind,
                quality_report=quality_report,
                required_fields=repair_required_fields,
                output_dir=output_dir,
                repair_records=repair_records,
                source_artifact_paths=source_artifact_paths,
            )
            repair_records.extend(repair_result.repair_records)
            repair_report_path = output_dir / "artifact_repair_report.json"
            repair_report_path.write_text(
                json.dumps(repair_result.report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            service._update_status(
                run_id,
                RunPhase.running,
                progress=94,
                repair_records=repair_records,
                attempt_no=service._max_attempt_no(repair_records),
                healing_summary=service._build_healing_summary(repair_records),
                plan_revision=service._extract_plan_revision(plan),
                checkpoint=service._checkpoint(stage="artifact_repair", plan_revision=service._extract_plan_revision(plan)),
                event_kind="artifact_repair_applied" if repair_result.changed else "artifact_repair_exhausted",
                event_message=(
                    "Artifact repair applied; quality gate will be re-evaluated."
                    if repair_result.changed
                    else "Artifact repair found no applicable safe strategy."
                ),
                event_details={
                    "input_path": str(fused_shp),
                    "output_path": str(repair_result.output_path),
                    "report_path": str(repair_report_path),
                    "applied_strategies": repair_result.applied_strategies,
                },
            )
            if repair_result.changed:
                fused_shp = repair_result.output_path
                quality_report = service.quality_gate_service.evaluate(
                    artifact_path=fused_shp,
                    task_kind=task_kind,
                    required_fields=required_fields,
                    requested_bbox=requested_bbox,
                    component_coverage=component_coverage,
                    source_artifact_paths=source_artifact_paths,
                    degradation_context=degradation_context,
                    quality_policy_id=quality_policy_id,
                    contract_id=contract_id,
                    source_expected_null_rates=source_expected_null_rates,
                )
                service._update_status(
                    run_id,
                    RunPhase.running,
                    progress=95,
                    repair_records=repair_records,
                    attempt_no=service._max_attempt_no(repair_records),
                    healing_summary=service._build_healing_summary(repair_records),
                    plan_revision=service._extract_plan_revision(plan),
                    checkpoint=service._checkpoint(stage="quality_gate", plan_revision=service._extract_plan_revision(plan)),
                    event_kind="quality_gate_evaluated",
                    event_message="Fusion output re-evaluated by quality gate after artifact repair.",
                    event_details={
                        "accepted": quality_report.accepted,
                        "policy_id": quality_report.policy_id,
                        "path": str(quality_report_path),
                        "feature_alignment_path": str(feature_alignment_path),
                        "failure_reasons": quality_report.failure_reasons,
                        "policy_adaptations": quality_report.policy_adaptations,
                        "repaired_artifact_path": str(fused_shp),
                    },
                )
        quality_report_path.write_text(
            json.dumps(quality_report.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        feature_alignment_path.write_text(
            json.dumps(quality_report.metrics.get("feature_alignment", {}), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if not quality_report.accepted:
            raise RuntimeError("Quality gate rejected fusion output")
        return fused_shp


def _task_kind_for_request(request: RunCreateRequest) -> TaskKind:
    preferred = str(request.preferred_pattern_id or "")
    if "waterways" in preferred:
        return TaskKind.waterways
    if "water_polygon" in preferred:
        return TaskKind.water_polygon
    expanded = expand_job_type_to_task_kinds(request.job_type)
    return expanded[0]


def _component_coverage_from_status(status) -> dict[str, object]:
    if status is None:
        return {}
    checkpoint = getattr(status, "checkpoint", None) or {}
    if isinstance(checkpoint, dict):
        coverage = checkpoint.get("component_coverage")
        if isinstance(coverage, dict):
            return coverage
    telemetry = getattr(status, "planning_telemetry", None) or {}
    if isinstance(telemetry, dict):
        coverage = telemetry.get("component_coverage")
        if isinstance(coverage, dict):
            return coverage
    return {}


def _source_artifact_paths_from_component_coverage(component_coverage: dict[str, object] | None) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for source_id, payload in (component_coverage or {}).items():
        raw_path = payload.get("path") if isinstance(payload, dict) else getattr(payload, "path", None)
        if not raw_path:
            continue
        path = Path(str(raw_path))
        if path.exists() and path.suffix.lower() in {".gpkg", ".shp", ".zip", ".geojson", ".json"}:
            paths[str(source_id)] = path
    return paths


def _merge_required_fields(primary: list[str], secondary: list[str]) -> list[str]:
    result: list[str] = []
    for field in [*primary, *secondary]:
        if field not in result:
            result.append(field)
    return result
