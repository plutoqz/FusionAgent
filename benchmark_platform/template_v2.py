from __future__ import annotations

from typing import Any, Mapping

from jsonschema import Draft202012Validator
from pydantic import BaseModel, ConfigDict

from benchmark_platform.models import BenchmarkPlatformValidationError, FailureClass, FailureRecord


REQUIRED_EXTENSIONS = {
    "TF-ALGORITHM-CAPABILITY-GROUNDING": ("algorithm_grounding",),
    "TF-AOI-RESOLUTION-BOUNDARY": ("aoi",),
    "TF-VECTOR-ACQUISITION-FAILURE": ("acquisition", "delivery"),
    "TF-QUALITY-GATE-EVIDENCE": ("acquisition", "algorithm_grounding", "quality_evidence", "delivery"),
    "TF-EVIDENCE-COMPLETENESS": ("aoi", "acquisition", "algorithm_grounding", "quality_evidence", "delivery"),
    "TF-DELIVERY-STATE-TRACE": ("quality_evidence", "delivery"),
}


class V2TemplateValidationError(BenchmarkPlatformValidationError):
    pass


class V2ExtensionValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_template_id: str
    schema_valid: bool
    lineage_valid: bool
    required_extensions_valid: bool
    passed: bool


def _fail(code: str, message: str, path: tuple[str | int, ...] = ()) -> None:
    raise V2TemplateValidationError([FailureRecord(failure_class=FailureClass.RUNTIME_INVALID_STATE, message=message, path=path, validator="template_v2", details={"code": code})])


def semantic_failures(document: Mapping[str, Any], required_extensions: tuple[str, ...] | None = None) -> tuple[str, ...]:
    failures: list[str] = []
    extensions = document.get("v2_extensions", {})
    lineage = document.get("lineage_binding", {})
    if not isinstance(extensions, Mapping) or not isinstance(lineage, Mapping):
        return ("missing_extension_or_lineage",)
    source_ids = set(lineage.get("source_ids", [])); algorithm_ids = set(lineage.get("algorithm_ids", [])); artifact_hashes = set(lineage.get("artifact_hashes", []))
    expected = required_extensions if required_extensions is not None else REQUIRED_EXTENSIONS.get(str(document.get("base_template_id")), ())
    for name in expected:
        if name not in extensions: failures.append(f"missing_required_extension:{name}")
    task_ids: set[str] = set()
    acquisition = extensions.get("acquisition", [])
    if isinstance(acquisition, list):
        for attempt in acquisition:
            if not isinstance(attempt, Mapping): continue
            task_id = str(attempt.get("task_id", ""))
            task_ids.add(task_id)
            if attempt.get("source_id") not in source_ids: failures.append("acquisition_source_not_in_lineage")
            if attempt.get("artifact_hash") and attempt.get("artifact_hash") not in artifact_hashes: failures.append("acquisition_artifact_not_in_lineage")
    groundings = extensions.get("algorithm_grounding", [])
    grounding_items = groundings if isinstance(groundings, list) else [groundings] if isinstance(groundings, Mapping) else []
    if grounding_items:
        grounding_tasks: set[str] = set()
        for grounding in grounding_items:
            if not isinstance(grounding, Mapping): continue
            task_id = str(grounding.get("task_id", ""))
            if task_id in grounding_tasks: failures.append("duplicate_algorithm_task")
            grounding_tasks.add(task_id)
            required = set(grounding.get("required_input_source_ids", [])); materialized = set(grounding.get("materialized_input_source_ids", [])); missing = set(grounding.get("missing_required_input_source_ids", []))
            if grounding.get("selected_algorithm_id") not in algorithm_ids: failures.append("algorithm_not_in_lineage")
            if not (required | materialized | missing).issubset(source_ids): failures.append("algorithm_source_not_in_lineage")
            if missing != required - materialized: failures.append("algorithm_missing_input_mismatch")
            if grounding.get("capability_status") == "compatible" and not required.issubset(materialized): failures.append("compatible_algorithm_missing_input")
    qualities = extensions.get("quality_evidence", [])
    quality_items = qualities if isinstance(qualities, list) else [qualities] if isinstance(qualities, Mapping) else []
    quality_by_task: dict[str, Mapping[str, Any]] = {}
    if quality_items:
        for quality in quality_items:
            if not isinstance(quality, Mapping): continue
            task_id = str(quality.get("task_id", ""))
            if task_id in quality_by_task: failures.append("duplicate_quality_task")
            quality_by_task[task_id] = quality
            if not set(quality.get("source_ids", [])).issubset(source_ids): failures.append("quality_source_not_in_lineage")
    deliveries = extensions.get("delivery", [])
    delivery_items = deliveries if isinstance(deliveries, list) else [deliveries] if isinstance(deliveries, Mapping) else []
    if delivery_items:
        delivery_tasks: set[str] = set()
        for delivery in delivery_items:
            if not isinstance(delivery, Mapping): continue
            task_id = str(delivery.get("task_id", ""))
            if task_id in delivery_tasks: failures.append("duplicate_delivery_task")
            delivery_tasks.add(task_id)
            if delivery.get("to_state") != "final": continue
            quality = quality_by_task.get(task_id)
            hard_statuses = {item.get("status") for item in quality.get("hard_checks", []) if isinstance(item, Mapping)} if isinstance(quality, Mapping) else set()
            if not quality or quality.get("quality_gate_result") != "pass" or hard_statuses != {"pass"}: failures.append("final_without_passing_quality")
            if delivery.get("terminal") is not True: failures.append("final_not_terminal")
    return tuple(failures)


def validate_v2_extension_document(document: Mapping[str, Any], schema: Mapping[str, Any]) -> V2ExtensionValidationReport:
    errors = tuple(Draft202012Validator(schema).iter_errors(document))
    if errors:
        first = errors[0]
        _fail("schema_invalid", first.message, tuple(first.absolute_path))
    failures = semantic_failures(document)
    if failures:
        _fail("semantic_invalid", "; ".join(failures))
    base_template_id = str(document.get("base_template_id"))
    return V2ExtensionValidationReport(base_template_id=base_template_id, schema_valid=True, lineage_valid=True, required_extensions_valid=True, passed=True)
