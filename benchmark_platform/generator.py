from __future__ import annotations

import json
from typing import Any, Mapping, Literal

from pydantic import BaseModel, ConfigDict, Field

from benchmark_platform.canonical import canonical_sha256, derive_seed
from benchmark_platform.crosswalk import validate_crosswalk
from benchmark_platform.design_loader import FrozenDesignBundle
from benchmark_platform.models import (
    BenchmarkPlatformValidationError,
    FailureClass,
    FailureRecord,
    SeedDerivationInput,
    validate_template_document,
)


MASTER_SEED = 2026081901
SEED_NAMESPACE = "fusionagent-benchmark-v1-development"
MAX_ATTEMPTS = 3
UNIT_TYPES = ("single", "counterfactual_pair", "invariant_set", "composition_family", "temporal_trace")


class GeneratorError(BenchmarkPlatformValidationError):
    """Raised when development generation cannot proceed safely."""


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    partition: str
    capability_cell_id: str = Field(pattern=r"^BC-[A-Z0-9-]+$")
    unit_index: int = Field(ge=0)
    seed_namespace: str = Field(min_length=1)
    master_seed: int = Field(ge=0)
    max_attempts: int = Field(default=MAX_ATTEMPTS, ge=1)


class GeneratedMember(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    member_index: int = Field(ge=0)
    member_payload: dict[str, Any]
    member_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class GeneratedUnit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    instance_id: str = Field(pattern=r"^BDV1-DEV-BC-[A-Z0-9-]+-[0-9]{3}$")
    template_family_id: str
    capability_cell_id: str
    partition: Literal["development"]
    unit_index: int = Field(ge=0)
    unit_type: Literal["single", "counterfactual_pair", "invariant_set", "composition_family", "temporal_trace"]
    seed: int = Field(ge=0)
    template_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    members: tuple[GeneratedMember, ...] = Field(min_length=1)
    instance_sha256: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


class GenerationAttempt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attempt_index: int = Field(ge=0)
    partition: str
    capability_cell_id: str
    unit_index: int = Field(ge=0)
    status: Literal["valid", "failed_retained"]
    seed: int = Field(ge=0)
    instance_id: str | None = None
    instance_sha256: str | None = None
    failure: FailureRecord | None = None


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attempts: tuple[GenerationAttempt, ...] = Field(min_length=1)
    units: tuple[GeneratedUnit, ...]
    blockers: tuple[FailureRecord, ...] = ()


def _fail(code: str, message: str, path: tuple[str | int, ...] = ()) -> GeneratorError:
    return GeneratorError(
        [
            FailureRecord(
                failure_class=FailureClass.RUNTIME_INVALID_STATE,
                message=message,
                path=path,
                validator="generator",
                details={"code": code},
            )
        ]
    )


def _cell(bundle: FrozenDesignBundle, cell_id: str) -> dict[str, Any]:
    cells = bundle.matrix.get("cells", [])
    matches = [item for item in cells if isinstance(item, dict) and item.get("capability_cell_id") == cell_id]
    if len(matches) != 1:
        raise _fail("unknown_cell", f"capability cell is not uniquely frozen: {cell_id}")
    return matches[0]


def _development_partition(bundle: FrozenDesignBundle) -> dict[str, Any]:
    partitions = bundle.selection.get("partitions", [])
    matches = [item for item in partitions if isinstance(item, dict) and item.get("partition_id") == "development"]
    if len(matches) != 1:
        raise _fail("seed_mismatch", "frozen development partition is not uniquely defined")
    return matches[0]


def _instance_id(cell_id: str, unit_index: int) -> str:
    return f"BDV1-DEV-{cell_id}-{unit_index:03d}"


def _member_count(template: Mapping[str, Any]) -> int:
    unit = template.get("experiment_unit")
    if not isinstance(unit, Mapping) or unit.get("unit_type") not in UNIT_TYPES:
        raise _fail("invalid_member", "template experiment unit has an unknown unit type")
    minimum = unit.get("minimum_members")
    if not isinstance(minimum, int) or minimum < 1:
        raise _fail("invalid_member", "template minimum_members must be a positive integer")
    if unit["unit_type"] != "single" and minimum < 2:
        raise _fail("invalid_member", "relational units require at least two members")
    return minimum


def generate_development(
    bundle: FrozenDesignBundle,
    template: Mapping[str, Any],
    request: GenerationRequest,
) -> GenerationResult:
    """Generate one deterministic development unit entirely in memory."""
    if request.partition != "development":
        raise _fail("non_development_partition", "only the development partition is authorized")
    if request.max_attempts > MAX_ATTEMPTS:
        raise _fail("attempt_limit", f"max_attempts cannot exceed frozen limit {MAX_ATTEMPTS}")
    partition = _development_partition(bundle)
    if request.seed_namespace != partition.get("seed_namespace") or request.seed_namespace != SEED_NAMESPACE:
        raise _fail("seed_mismatch", "request seed namespace differs from frozen development namespace")
    if request.master_seed != partition.get("master_seed") or request.master_seed != MASTER_SEED:
        raise _fail("seed_mismatch", "request master seed differs from frozen development seed")
    cell = _cell(bundle, request.capability_cell_id)
    try:
        validate_template_document(template, bundle.schema_document)
        validate_crosswalk(bundle, template)
    except BenchmarkPlatformValidationError as error:
        raise _fail("invalid_member", "template validation or crosswalk failed") from error
    if request.capability_cell_id not in template.get("capability_cell_ids", []):
        raise _fail("invalid_member", "template does not declare the requested capability cell")
    if template.get("status") != "frozen_template_family":
        raise _fail("invalid_member", "template status is not frozen_template_family")

    unit_type = str(template["experiment_unit"]["unit_type"])
    count = _member_count(template)
    seed = derive_seed(SeedDerivationInput(namespace=f"{request.seed_namespace}:{request.capability_cell_id}", master_seed=request.master_seed, unit_index=request.unit_index))
    template_hash = canonical_sha256(template)
    members: list[GeneratedMember] = []
    for index in range(count):
        payload = json.loads(json.dumps(template, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        members.append(GeneratedMember(member_index=index, member_payload=payload, member_sha256=canonical_sha256(payload)))
    instance_id = _instance_id(request.capability_cell_id, request.unit_index)
    identity_payload = {
        "instance_id": instance_id,
        "template_family_id": template.get("template_family_id"),
        "capability_cell_id": request.capability_cell_id,
        "partition": request.partition,
        "unit_index": request.unit_index,
        "unit_type": unit_type,
        "seed": seed,
        "template_sha256": template_hash,
        "members": [member.model_dump(mode="json") for member in members],
    }
    instance_hash = canonical_sha256(identity_payload)
    unit = GeneratedUnit(
        instance_id=instance_id,
        template_family_id=str(template["template_family_id"]),
        capability_cell_id=request.capability_cell_id,
        partition="development",
        unit_index=request.unit_index,
        unit_type=unit_type,
        seed=seed,
        template_sha256=template_hash,
        members=tuple(members),
        instance_sha256=instance_hash,
    )
    attempt = GenerationAttempt(
        attempt_index=0,
        partition=request.partition,
        capability_cell_id=request.capability_cell_id,
        unit_index=request.unit_index,
        status="valid",
        seed=seed,
        instance_id=instance_id,
        instance_sha256=instance_hash,
    )
    return GenerationResult(attempts=(attempt,), units=(unit,), blockers=())


generate_development_unit = generate_development
