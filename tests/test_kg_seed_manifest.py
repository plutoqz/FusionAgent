from __future__ import annotations

from kg.seed_manifest import build_seed_manifest_payload, load_seed_manifest_payload
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


def test_build_seed_manifest_payload_contains_current_seed_ids() -> None:
    payload = build_seed_manifest_payload()

    algorithm_ids = {item["algo_id"] for item in payload["algorithms"]}
    data_source_ids = {item["source_id"] for item in payload["data_sources"]}

    assert "algo.fusion.building.v1" in algorithm_ids
    assert "raw.osm.building" in data_source_ids
    assert payload["metadata"]["schema_version"] == "1.0.0"
    assert payload["metadata"]["content_hash"].startswith("sha256:")


def test_load_seed_manifest_payload_reconstructs_core_dataclasses() -> None:
    payload = build_seed_manifest_payload()
    loaded = load_seed_manifest_payload(payload)

    assert "algo.fusion.building.v1" in loaded["algorithms"]
    assert loaded["algorithms"]["algo.fusion.building.v1"].algo_id == "algo.fusion.building.v1"
    assert loaded["workflow_patterns"]
    assert loaded["output_schema_policies"]
