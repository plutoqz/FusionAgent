from __future__ import annotations

from collections.abc import Mapping, Sequence
from enum import Enum
from typing import Any, Literal

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError as JsonSchemaValidationError
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, field_validator


class FailureClass(str, Enum):
    SCHEMA_INVALID = "schema.invalid_schema"
    SCHEMA_DOCUMENT_INVALID = "schema.document_invalid"
    RUNTIME_UNKNOWN_FIELD = "runtime.unknown_field"
    RUNTIME_INVALID_STATE = "runtime.invalid_state"
    RUNTIME_DUPLICATE_ID = "runtime.duplicate_id"
    CANONICAL_UNSUPPORTED_TYPE = "canonical.unsupported_type"
    CANONICAL_NON_FINITE_NUMBER = "canonical.non_finite_number"


class StrictRuntimeModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FailureRecord(StrictRuntimeModel):
    failure_class: FailureClass
    message: str = Field(min_length=1)
    path: tuple[str | int, ...] = ()
    validator: str | None = None
    details: dict[str, JsonValue] = Field(default_factory=dict)


class BenchmarkPlatformValidationError(ValueError):
    def __init__(self, failures: Sequence[FailureRecord]) -> None:
        if not failures:
            raise ValueError("at least one failure record is required")
        self.failures = tuple(failures)
        super().__init__("; ".join(f"{item.failure_class.value}: {item.message}" for item in self.failures))


ClaimId = Literal[
    "CL-BENCH-CAUSAL",
    "CL-BENCH-INVARIANT",
    "CL-BENCH-COMPOSE",
    "CL-BENCH-RECOVERY",
    "CL-BENCH-DIAG",
]
ComplexityLevel = Literal["L0", "L1", "L2", "L3", "L4"]


class TemplateRuntimeDocument(StrictRuntimeModel):
    template_family_id: str = Field(pattern=r"^TF-[A-Z0-9-]+$")
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    status: Literal["frozen_template_family"]
    claim_ids: tuple[ClaimId, ...] = Field(min_length=1)
    capability_cell_ids: tuple[str, ...] = Field(min_length=1)
    mechanism_family: str = Field(min_length=1)
    complexity_level: ComplexityLevel
    experiment_unit: dict[str, JsonValue]
    provenance: dict[str, JsonValue]
    task_state: dict[str, JsonValue]
    variables: dict[str, JsonValue]
    oracle: dict[str, JsonValue]
    vetoes: tuple[dict[str, JsonValue], ...] = Field(min_length=1)
    views: dict[str, JsonValue]
    crosswalk: dict[str, JsonValue]
    partition_policy: dict[str, JsonValue]
    generation: dict[str, JsonValue]
    hashing: dict[str, JsonValue]
    e2e_eligibility: dict[str, JsonValue] | None = None

    @field_validator("claim_ids", "capability_cell_ids")
    @classmethod
    def _ids_must_be_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("duplicate identifiers are forbidden")
        return values


class CanonicalIdentity(StrictRuntimeModel):
    design_id: str = Field(min_length=1)
    template_family_id: str = Field(pattern=r"^TF-[A-Z0-9-]+$")
    capability_cell_id: str = Field(pattern=r"^BC-[A-Z0-9-]+$")
    partition: Literal["development"]
    unit_index: int = Field(ge=0)
    seed: int = Field(ge=0)
    payload: dict[str, JsonValue]


class SeedDerivationInput(StrictRuntimeModel):
    namespace: str = Field(min_length=1)
    master_seed: int = Field(ge=0)
    unit_index: int = Field(ge=0)


def _jsonschema_failure_class(error: JsonSchemaValidationError) -> FailureClass:
    if error.validator == "additionalProperties":
        return FailureClass.RUNTIME_UNKNOWN_FIELD
    if error.validator == "uniqueItems":
        return FailureClass.RUNTIME_DUPLICATE_ID
    if error.validator in {"const", "enum"}:
        return FailureClass.RUNTIME_INVALID_STATE
    return FailureClass.SCHEMA_DOCUMENT_INVALID


def _schema_error_record(error: SchemaError) -> FailureRecord:
    return FailureRecord(
        failure_class=FailureClass.SCHEMA_INVALID,
        message=error.message,
        path=tuple(error.absolute_schema_path),
        validator=str(error.validator) if error.validator is not None else None,
    )


def _document_error_record(error: JsonSchemaValidationError) -> FailureRecord:
    return FailureRecord(
        failure_class=_jsonschema_failure_class(error),
        message=error.message,
        path=tuple(error.absolute_path),
        validator=str(error.validator) if error.validator is not None else None,
    )


def _runtime_error_records(error: ValidationError) -> tuple[FailureRecord, ...]:
    failures: list[FailureRecord] = []
    for item in error.errors(include_url=False, include_context=False, include_input=False):
        error_type = str(item["type"])
        message = str(item["msg"])
        if error_type == "extra_forbidden":
            failure_class = FailureClass.RUNTIME_UNKNOWN_FIELD
        elif "duplicate identifiers" in message:
            failure_class = FailureClass.RUNTIME_DUPLICATE_ID
        else:
            failure_class = FailureClass.RUNTIME_INVALID_STATE
        failures.append(
            FailureRecord(
                failure_class=failure_class,
                message=message,
                path=tuple(item["loc"]),
                validator=error_type,
            )
        )
    return tuple(failures)


def validate_template_document(
    document: Mapping[str, Any], schema: Mapping[str, Any]
) -> TemplateRuntimeDocument:
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as error:
        raise BenchmarkPlatformValidationError([_schema_error_record(error)]) from error

    validator = Draft202012Validator(schema)
    schema_errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (tuple(str(item) for item in error.absolute_path), error.message),
    )
    if schema_errors:
        raise BenchmarkPlatformValidationError([_document_error_record(error) for error in schema_errors])

    try:
        return TemplateRuntimeDocument.model_validate(document)
    except ValidationError as error:
        raise BenchmarkPlatformValidationError(_runtime_error_records(error)) from error
