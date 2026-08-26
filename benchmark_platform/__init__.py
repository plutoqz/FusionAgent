"""Bounded offline benchmark platform primitives."""

from benchmark_platform.canonical import (
    CanonicalizationError,
    canonical_json_bytes,
    canonical_json_text,
    canonical_sha256,
    derive_seed,
    stable_id,
)
from benchmark_platform.models import (
    BenchmarkPlatformValidationError,
    CanonicalIdentity,
    FailureClass,
    FailureRecord,
    SeedDerivationInput,
    TemplateRuntimeDocument,
    validate_template_document,
)

__all__ = [
    "BenchmarkPlatformValidationError",
    "CanonicalIdentity",
    "CanonicalizationError",
    "FailureClass",
    "FailureRecord",
    "SeedDerivationInput",
    "TemplateRuntimeDocument",
    "canonical_json_bytes",
    "canonical_json_text",
    "canonical_sha256",
    "derive_seed",
    "stable_id",
    "validate_template_document",
]
