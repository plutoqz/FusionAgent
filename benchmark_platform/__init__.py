"""Bounded offline benchmark platform primitives."""

from benchmark_platform.canonical import (
    CanonicalizationError,
    canonical_json_bytes,
    canonical_json_text,
    canonical_sha256,
    derive_seed,
    stable_id,
)
from benchmark_platform.crosswalk import (
    CrosswalkBinding,
    CrosswalkError,
    CrosswalkReport,
    build_crosswalk_registry,
    validate_crosswalk,
)
from benchmark_platform.design_loader import (
    DESIGN_COMMIT,
    DESIGN_ID,
    DESIGN_TAG,
    FREEZE_ID,
    KG_RELEASE_ID,
    KG_SEMANTIC_HASH,
    DesignLoaderError,
    FrozenDesignBundle,
    load_frozen_design_bundle,
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
    "CrosswalkBinding",
    "CrosswalkError",
    "CrosswalkReport",
    "CanonicalIdentity",
    "CanonicalizationError",
    "FailureClass",
    "FailureRecord",
    "DesignLoaderError",
    "FrozenDesignBundle",
    "SeedDerivationInput",
    "TemplateRuntimeDocument",
    "canonical_json_bytes",
    "canonical_json_text",
    "canonical_sha256",
    "derive_seed",
    "stable_id",
    "validate_template_document",
    "build_crosswalk_registry",
    "validate_crosswalk",
    "load_frozen_design_bundle",
    "DESIGN_TAG",
    "DESIGN_COMMIT",
    "DESIGN_ID",
    "FREEZE_ID",
    "KG_RELEASE_ID",
    "KG_SEMANTIC_HASH",
]
