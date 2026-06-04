from __future__ import annotations

from schemas.kg_seed_manifest import KgSeedManifest, KgSeedManifestMetadata


def test_kg_seed_manifest_requires_versioned_metadata() -> None:
    manifest = KgSeedManifest(
        metadata=KgSeedManifestMetadata(
            schema_version="1.0.0",
            generated_from="kg.seed",
            content_hash="sha256:test",
        ),
        data_types=[],
        tasks=[],
        scenario_profiles=[],
        algorithms=[],
        parameter_specs=[],
        workflow_patterns=[],
        data_sources=[],
        output_schema_policies=[],
    )

    payload = manifest.model_dump(mode="json")

    assert payload["metadata"]["schema_version"] == "1.0.0"
    assert payload["metadata"]["content_hash"] == "sha256:test"
