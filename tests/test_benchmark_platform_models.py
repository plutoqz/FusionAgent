from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from benchmark_platform.models import (
    BenchmarkPlatformValidationError,
    CanonicalIdentity,
    FailureClass,
    FailureRecord,
    TemplateRuntimeDocument,
    validate_template_document,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "docs/current/benchmark/v1/template.schema.json"
FIXTURE_PATH = REPO_ROOT / "tests/fixtures/benchmark_platform/template_contract_valid.json"


def load_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def test_frozen_draft_2020_12_schema_accepts_contract_fixture() -> None:
    document = load_object(FIXTURE_PATH)
    model = validate_template_document(document, load_object(SCHEMA_PATH))
    assert isinstance(model, TemplateRuntimeDocument)
    assert model.template_family_id == "TF-CONTRACT-FIXTURE"
    assert model.capability_cell_ids == ("BC-CAUSAL-01",)


def test_unknown_root_and_nested_fields_fail_closed_with_typed_records() -> None:
    schema = load_object(SCHEMA_PATH)
    root_unknown = load_object(FIXTURE_PATH)
    root_unknown["unexpected"] = True
    with pytest.raises(BenchmarkPlatformValidationError) as root_error:
        validate_template_document(root_unknown, schema)
    assert FailureClass.RUNTIME_UNKNOWN_FIELD in {
        failure.failure_class for failure in root_error.value.failures
    }

    nested_unknown = load_object(FIXTURE_PATH)
    nested_unknown["task_state"]["tasks"][0]["unexpected"] = True
    with pytest.raises(BenchmarkPlatformValidationError) as nested_error:
        validate_template_document(nested_unknown, schema)
    unknown = next(
        failure
        for failure in nested_error.value.failures
        if failure.failure_class == FailureClass.RUNTIME_UNKNOWN_FIELD
    )
    assert unknown.path == ("task_state", "tasks", 0)


def test_invalid_schema_and_duplicate_ids_have_distinct_failure_classes() -> None:
    invalid_schema = {"type": "not-a-json-schema-type"}
    with pytest.raises(BenchmarkPlatformValidationError) as schema_error:
        validate_template_document(load_object(FIXTURE_PATH), invalid_schema)
    assert [item.failure_class for item in schema_error.value.failures] == [
        FailureClass.SCHEMA_INVALID
    ]

    duplicate = load_object(FIXTURE_PATH)
    duplicate["claim_ids"] = ["CL-BENCH-CAUSAL", "CL-BENCH-CAUSAL"]
    with pytest.raises(BenchmarkPlatformValidationError) as duplicate_error:
        validate_template_document(duplicate, load_object(SCHEMA_PATH))
    assert FailureClass.RUNTIME_DUPLICATE_ID in {
        failure.failure_class for failure in duplicate_error.value.failures
    }


def test_runtime_models_forbid_unknown_fields() -> None:
    with pytest.raises(ValidationError) as identity_error:
        CanonicalIdentity.model_validate(
            {
                "design_id": "fusionagent.benchmark-design.v1",
                "template_family_id": "TF-CONTRACT-FIXTURE",
                "capability_cell_id": "BC-CAUSAL-01",
                "partition": "development",
                "unit_index": 0,
                "seed": 1,
                "payload": {},
                "unexpected": True,
            }
        )
    assert identity_error.value.errors()[0]["type"] == "extra_forbidden"

    with pytest.raises(ValidationError):
        FailureRecord.model_validate(
            {
                "failure_class": "runtime.invalid_state",
                "message": "invalid",
                "unexpected": True,
            }
        )


def test_runtime_envelope_rejects_invalid_state_without_schema_fallback() -> None:
    document = load_object(FIXTURE_PATH)
    document["status"] = "draft"
    with pytest.raises(ValidationError):
        TemplateRuntimeDocument.model_validate(document)


def test_fixture_is_explicitly_not_a_benchmark_instance_or_claim_evidence() -> None:
    readme = (FIXTURE_PATH.parent / "README.md").read_text(encoding="utf-8")
    assert "不是 benchmark instance" in readme
    assert "不能支持研究主张" in readme
    assert "instance_id" not in load_object(FIXTURE_PATH)
