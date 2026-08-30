from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from benchmark_platform.canonical import canonical_json_text, canonical_sha256
from benchmark_platform.crosswalk import validate_crosswalk
from benchmark_platform.design_loader import FrozenDesignBundle, load_frozen_design_bundle
from benchmark_platform.generator import GenerationRequest, GeneratedUnit, generate_development
from benchmark_platform.models import BenchmarkPlatformValidationError, validate_template_document
from benchmark_platform.relations import validate_relations
from benchmark_platform.store import (
    RUN_STAGES,
    ArtifactStore,
    ResumeRequest,
    RunBinding,
    RunCheckpoint,
)
from benchmark_platform.views import project_views


EXIT_OK = 0
EXIT_USAGE = 2
EXIT_VALIDATION = 3
EXIT_INTERNAL = 4


class CliUsageError(ValueError):
    pass


class CliValidationError(ValueError):
    pass


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliUsageError(message)


def _read_object(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CliValidationError(f"cannot read JSON object: {path}") from error
    if not isinstance(value, dict):
        raise CliValidationError(f"expected JSON object: {path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        values = [json.loads(line) for line in lines if line.strip()]
    except (OSError, json.JSONDecodeError) as error:
        raise CliValidationError(f"cannot read JSONL stream: {path}") from error
    if any(not isinstance(value, dict) for value in values):
        raise CliValidationError(f"JSONL stream contains a non-object: {path}")
    return values


def _write_stdout(payload: dict[str, Any]) -> None:
    sys.stdout.write(canonical_json_text(payload) + "\n")


def _write_stderr(payload: dict[str, Any]) -> None:
    sys.stderr.write(canonical_json_text(payload) + "\n")


def _bundle(args: argparse.Namespace) -> FrozenDesignBundle:
    return load_frozen_design_bundle(
        args.design_root,
        repo_root=args.repo_root,
    )


def _template(bundle: FrozenDesignBundle, path: str) -> dict[str, Any]:
    document = _read_object(path)
    validate_template_document(document, bundle.schema_document)
    return document


def _checkpoint(run_root: str | Path) -> RunCheckpoint:
    try:
        return RunCheckpoint.model_validate(_read_object(Path(run_root) / "checkpoint.json"))
    except ValidationError as error:
        raise CliValidationError("checkpoint does not satisfy the runtime contract") from error


def _binding(
    *,
    checkpoint: RunCheckpoint | None,
    run_id: str | None,
    bundle: FrozenDesignBundle,
    template: dict[str, Any],
    code_revision: str,
) -> RunBinding:
    effective_run_id = checkpoint.binding.run_id if checkpoint is not None else run_id
    if effective_run_id is None:
        raise CliValidationError("run ID is required")
    design_sha256 = canonical_sha256(bundle.manifest)
    template_sha256 = canonical_sha256(template)
    return RunBinding(
        run_id=effective_run_id,
        design_id=bundle.design_id,
        design_sha256=design_sha256,
        template_sha256=template_sha256,
        seed_namespace="fusionagent-benchmark-v1-development",
        master_seed=2026081901,
        code_revision=code_revision,
        input_hashes={"design": design_sha256, "template": template_sha256},
    )


def _resume_inputs(args: argparse.Namespace) -> tuple[ArtifactStore, RunCheckpoint, FrozenDesignBundle, dict[str, Any], RunBinding]:
    checkpoint = _checkpoint(args.run_root)
    bundle = _bundle(args)
    template = _template(bundle, args.template)
    binding = _binding(
        checkpoint=checkpoint,
        run_id=None,
        bundle=bundle,
        template=template,
        code_revision=args.code_revision,
    )
    store = ArtifactStore(Path(args.run_root))
    store.resume(ResumeRequest(run_root=str(store.root), expected_stage=checkpoint.stage, binding=binding))
    return store, checkpoint, bundle, template, binding


def _template_snapshot(run_root: Path) -> Path:
    snapshots = sorted((run_root / "template_snapshots").glob("*.json"))
    if len(snapshots) != 1:
        raise CliValidationError("run root must contain exactly one template snapshot")
    return snapshots[0]


def _allowed_failures(bundle: FrozenDesignBundle) -> set[str]:
    return {
        failure
        for gate in bundle.evaluation.get("gates", [])
        if isinstance(gate, dict)
        for failure in gate.get("failure_classes", [])
        if isinstance(failure, str)
    }


def _cell(bundle: FrozenDesignBundle, cell_id: str) -> dict[str, Any]:
    matches = [
        cell
        for cell in bundle.matrix.get("cells", [])
        if isinstance(cell, dict) and cell.get("capability_cell_id") == cell_id
    ]
    if len(matches) != 1:
        raise CliValidationError(f"capability cell is not uniquely frozen: {cell_id}")
    return matches[0]


def command_validate_design(args: argparse.Namespace) -> dict[str, Any]:
    bundle = _bundle(args)
    return {
        "command": "validate-design",
        "status": "ok",
        "design_id": bundle.design_id,
        "cell_count": len(bundle.matrix.get("cells", [])),
    }


def command_validate_template(args: argparse.Namespace) -> dict[str, Any]:
    bundle = _bundle(args)
    template = _template(bundle, args.template)
    crosswalk = validate_crosswalk(bundle, template)
    return {
        "command": "validate-template",
        "status": "ok",
        "template_family_id": template["template_family_id"],
        "reference_count": crosswalk.reference_count,
    }


def command_generate_development(args: argparse.Namespace) -> dict[str, Any]:
    bundle = _bundle(args)
    template = _template(bundle, args.template)
    binding = _binding(
        checkpoint=None,
        run_id=args.run_id,
        bundle=bundle,
        template=template,
        code_revision=args.code_revision,
    )
    result = generate_development(
        bundle,
        template,
        GenerationRequest(
            partition="development",
            capability_cell_id=args.capability_cell_id,
            unit_index=args.unit_index,
            seed_namespace=binding.seed_namespace,
            master_seed=binding.master_seed,
        ),
    )
    store = ArtifactStore.create_new(args.output_root, binding)
    store.commit_stage(
        "design_bound",
        input_hashes={"design": binding.design_sha256},
        output_paths=["design_binding.json"],
    )
    snapshot_name = f"template_snapshots/{template['template_family_id']}.json"
    store.write_json_artifact(snapshot_name, template)
    store.commit_stage(
        "templates_validated",
        input_hashes={"template": binding.template_sha256},
        output_paths=[snapshot_name],
    )
    for attempt in result.attempts:
        store.append_jsonl("generation_attempts.jsonl", attempt.model_dump(mode="json"))
    for unit in result.units:
        store.append_instance(unit.model_dump(mode="json"))
    store.commit_stage(
        "generated",
        input_hashes={"generator": canonical_sha256(result.model_dump(mode="json"))},
        output_paths=["generation_attempts.jsonl", "instances.jsonl"],
    )
    return {
        "command": "generate-development",
        "status": "ok",
        "run_id": binding.run_id,
        "stage": "generated",
        "unit_count": len(result.units),
        "run_root": str(store.root),
    }


def command_validate_run(args: argparse.Namespace) -> dict[str, Any]:
    store, checkpoint, bundle, template, _ = _resume_inputs(args)
    if checkpoint.stage != "generated":
        raise CliValidationError("validate-run requires a generated checkpoint")
    snapshot = _read_object(_template_snapshot(store.root))
    if canonical_sha256(snapshot) != canonical_sha256(template):
        raise CliValidationError("template snapshot differs from the expected template")
    units = [GeneratedUnit.model_validate(value) for value in _read_jsonl(store.root / "instances.jsonl")]
    reports: list[dict[str, Any]] = []
    allowed_failures = _allowed_failures(bundle)
    for unit in units:
        cell = _cell(bundle, unit.capability_cell_id)
        report = validate_relations(
            unit,
            template,
            str(cell["primary_failure_class"]),
            allowed_failures,
        )
        reports.append(report.model_dump(mode="json"))
    passed = bool(reports) and all(report.get("passed") is True for report in reports)
    if not passed:
        raise CliValidationError("one or more relation checks failed")
    store.write_json_artifact("validation_report.json", {"passed": True, "reports": reports})
    store.commit_stage(
        "relations_validated",
        input_hashes={"instances": canonical_sha256([unit.model_dump(mode="json") for unit in units])},
        output_paths=["validation_report.json"],
    )
    return {"command": "validate-run", "status": "ok", "stage": "relations_validated", "unit_count": len(units)}


def command_project_views(args: argparse.Namespace) -> dict[str, Any]:
    store, checkpoint, _, template, _ = _resume_inputs(args)
    if checkpoint.stage != "relations_validated":
        raise CliValidationError("project-views requires a relations_validated checkpoint")
    units = [GeneratedUnit.model_validate(value) for value in _read_jsonl(store.root / "instances.jsonl")]
    audits: list[dict[str, Any]] = []
    for unit in units:
        projected = project_views(unit.members[0].member_payload, template["views"])
        store.append_jsonl("planner_packets.jsonl", {"instance_id": unit.instance_id, **projected.planner.model_dump(mode="json")})
        store.append_jsonl("evaluator_packets.jsonl", {"instance_id": unit.instance_id, **projected.evaluator.model_dump(mode="json")})
        store.append_jsonl("human_blind_packets.jsonl", {"instance_id": unit.instance_id, **projected.human_blind.model_dump(mode="json")})
        audits.append(projected.leakage_audit.model_dump(mode="json"))
    passed = bool(audits) and all(audit.get("passed") is True for audit in audits)
    if not passed:
        raise CliValidationError("view projection leakage audit failed")
    store.write_json_artifact("leakage_audit.json", {"passed": True, "audits": audits})
    outputs = [
        "planner_packets.jsonl",
        "evaluator_packets.jsonl",
        "human_blind_packets.jsonl",
        "leakage_audit.json",
    ]
    store.commit_stage(
        "views_projected",
        input_hashes={"views": canonical_sha256(template["views"])},
        output_paths=outputs,
    )
    return {"command": "project-views", "status": "ok", "stage": "views_projected", "packet_count": len(units)}


def command_audit_run(args: argparse.Namespace) -> dict[str, Any]:
    store, checkpoint, _, _, _ = _resume_inputs(args)
    if checkpoint.stage != "views_projected":
        raise CliValidationError("audit-run requires a views_projected checkpoint")
    validation = _read_object(store.root / "validation_report.json")
    leakage = _read_object(store.root / "leakage_audit.json")
    if validation.get("passed") is not True or leakage.get("passed") is not True:
        raise CliValidationError("run reports are not audit-passing")
    store.commit_stage(
        "audited",
        input_hashes={"audit": canonical_sha256({"validation": validation, "leakage": leakage})},
        output_paths=["validation_report.json", "leakage_audit.json"],
    )
    store.commit_stage(
        "development_complete",
        input_hashes={"completion": canonical_sha256({"run_id": checkpoint.binding.run_id})},
        output_paths=[],
    )
    terminal = store.finalize()
    return {
        "command": "audit-run",
        "status": "ok",
        "stage": "development_complete",
        "terminal_binding": terminal.model_dump(mode="json"),
    }


def command_resume_development(args: argparse.Namespace) -> dict[str, Any]:
    store, checkpoint, _, _, binding = _resume_inputs(args)
    if checkpoint.stage != args.expected_stage:
        raise CliValidationError("checkpoint stage differs from the explicit expected stage")
    state = store.resume(
        ResumeRequest(run_root=str(store.root), expected_stage=args.expected_stage, binding=binding)
    )
    return {
        "command": "resume-development",
        "status": "ok",
        "stage": state.stage,
        "checkpoint_sha256": state.checkpoint_sha256,
    }


def _add_design_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--design-root", required=True)
    parser.add_argument("--repo-root")


def _add_run_args(parser: argparse.ArgumentParser) -> None:
    _add_design_args(parser)
    parser.add_argument("--template", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--code-revision", required=True)


def build_parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="benchmark-platform", description="Bounded offline benchmark utilities.")
    commands = parser.add_subparsers(dest="command", required=True)

    validate_design = commands.add_parser("validate-design")
    _add_design_args(validate_design)
    validate_design.set_defaults(handler=command_validate_design)

    validate_template = commands.add_parser("validate-template")
    _add_design_args(validate_template)
    validate_template.add_argument("--template", required=True)
    validate_template.set_defaults(handler=command_validate_template)

    generate = commands.add_parser("generate-development")
    _add_design_args(generate)
    generate.add_argument("--template", required=True)
    generate.add_argument("--output-root", required=True)
    generate.add_argument("--run-id", required=True)
    generate.add_argument("--capability-cell-id", required=True)
    generate.add_argument("--unit-index", required=True, type=int)
    generate.add_argument("--code-revision", required=True)
    generate.set_defaults(handler=command_generate_development)

    validate_run = commands.add_parser("validate-run")
    _add_run_args(validate_run)
    validate_run.set_defaults(handler=command_validate_run)

    project = commands.add_parser("project-views")
    _add_run_args(project)
    project.set_defaults(handler=command_project_views)

    audit = commands.add_parser("audit-run")
    _add_run_args(audit)
    audit.set_defaults(handler=command_audit_run)

    resume = commands.add_parser("resume-development")
    _add_run_args(resume)
    resume.add_argument("--expected-stage", required=True, choices=RUN_STAGES)
    resume.set_defaults(handler=command_resume_development)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = args.handler(args)
        _write_stdout(result)
        return EXIT_OK
    except CliUsageError as error:
        _write_stderr({"status": "error", "error_class": "usage", "message": str(error)})
        return EXIT_USAGE
    except (BenchmarkPlatformValidationError, CliValidationError, ValidationError, OSError) as error:
        _write_stderr({"status": "error", "error_class": "validation", "message": str(error)})
        return EXIT_VALIDATION
    except Exception as error:
        _write_stderr({"status": "error", "error_class": "internal", "message": type(error).__name__})
        return EXIT_INTERNAL


if __name__ == "__main__":
    raise SystemExit(main())
