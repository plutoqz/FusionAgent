from __future__ import annotations

import json
from pathlib import Path

from kg.seed_provider import RepositorySeedPayload, load_seed_data
from kg.seed_manifest import build_seed_manifest_payload, load_seed_manifest_payload
from scripts import export_kg_seed_manifest
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
    assert payload["metadata"]["source_modules"] == [
        "kg.seed",
        "fusion_algorithms.registry_metadata",
    ]
    assert payload["metadata"]["content_hash"].startswith("sha256:")


def test_load_seed_manifest_payload_reconstructs_core_dataclasses() -> None:
    payload = build_seed_manifest_payload()
    loaded = load_seed_manifest_payload(payload)

    assert "algo.fusion.building.v1" in loaded["algorithms"]
    assert loaded["algorithms"]["algo.fusion.building.v1"].algo_id == "algo.fusion.building.v1"
    assert loaded["workflow_patterns"]
    assert loaded["output_schema_policies"]


def test_checked_in_seed_manifest_matches_current_seed_id_sets() -> None:
    generated = json.loads(Path("kg/seed_manifest.generated.json").read_text(encoding="utf-8"))
    current = build_seed_manifest_payload()

    assert _ids(generated, "data_types", "type_id") == _ids(current, "data_types", "type_id")
    assert _ids(generated, "algorithms", "algo_id") == _ids(current, "algorithms", "algo_id")
    assert _ids(generated, "workflow_patterns", "pattern_id") == _ids(current, "workflow_patterns", "pattern_id")
    assert _ids(generated, "data_sources", "source_id") == _ids(current, "data_sources", "source_id")
    assert _ids(generated, "output_schema_policies", "policy_id") == _ids(
        current,
        "output_schema_policies",
        "policy_id",
    )


def test_export_check_ignores_generated_at_but_detects_manifest_drift() -> None:
    current = build_seed_manifest_payload()
    same_with_new_timestamp = json.loads(json.dumps(current, ensure_ascii=False, sort_keys=True))
    same_with_new_timestamp["metadata"]["generated_at"] = "2099-01-01T00:00:00+00:00"

    assert hasattr(export_kg_seed_manifest, "manifests_match")
    assert export_kg_seed_manifest.manifests_match(current, same_with_new_timestamp)

    drifted = json.loads(json.dumps(current, ensure_ascii=False, sort_keys=True))
    drifted["algorithms"][0]["metadata"]["handler_name"] = "stale_handler"

    assert not export_kg_seed_manifest.manifests_match(current, drifted)


def test_seed_provider_manifest_payload_matches_default_seed_counts_and_ids() -> None:
    manifest_path = Path("kg/seed_manifest.generated.json")

    default_seed = load_seed_data()
    manifest_seed = load_seed_data(manifest_path)

    assert set(default_seed) == set(RepositorySeedPayload.__annotations__)
    assert set(manifest_seed) == set(RepositorySeedPayload.__annotations__)
    assert _seed_stable_inventory(default_seed) == _seed_stable_inventory(manifest_seed)


def test_seed_provider_manifest_payload_keeps_python_seed_transform_graph() -> None:
    default_seed = load_seed_data()
    manifest_seed = load_seed_data(Path("kg/seed_manifest.generated.json"))

    assert _normalized_transform_edges(manifest_seed) == _normalized_transform_edges(default_seed)


def _ids(payload: dict, section: str, key: str) -> set[str]:
    return {str(item[key]) for item in payload[section]}


def _seed_stable_inventory(payload: dict[str, object]) -> dict[str, object]:
    return {
        "data_types": _mapping_ids(payload, "data_types", "type_id"),
        "algorithms": _mapping_ids(payload, "algorithms", "algo_id"),
        "parameter_specs": _parameter_spec_ids(payload),
        "patterns": _sequence_ids(payload, "patterns", "pattern_id"),
        "data_sources": _sequence_ids(payload, "data_sources", "source_id"),
        "output_schema_policies": _mapping_ids(payload, "output_schema_policies", "policy_id"),
        "tasks": _mapping_ids(payload, "tasks", "task_id"),
        "scenario_profiles": _sequence_ids(payload, "scenario_profiles", "profile_id"),
        "task_bundles": _mapping_ids(payload, "task_bundles", "bundle_id"),
        "output_requirements": _mapping_ids(payload, "output_requirements", "requirement_id"),
        "qos_policies": _mapping_ids(payload, "qos_policies", "policy_id"),
        "data_needs": _sequence_ids(payload, "data_needs", "need_id"),
        "repair_strategies": _mapping_ids(payload, "repair_strategies", "strategy_id"),
        "can_transform_to": _normalized_transform_edges(payload),
    }


def _mapping_ids(payload: dict[str, object], section: str, attr: str) -> list[str]:
    values = payload[section]
    assert isinstance(values, dict)
    return sorted(str(getattr(item, attr)) for item in values.values())


def _sequence_ids(payload: dict[str, object], section: str, attr: str) -> list[str]:
    values = payload[section]
    assert isinstance(values, list)
    return sorted(str(getattr(item, attr)) for item in values)


def _parameter_spec_ids(payload: dict[str, object]) -> list[tuple[str, int, str]]:
    values = payload["parameter_specs"]
    assert isinstance(values, dict)
    return sorted(
        (str(spec.algo_id), int(spec.order), str(spec.key))
        for specs in values.values()
        for spec in specs
    )


def _normalized_transform_edges(payload: dict[str, object]) -> dict[str, list[str]]:
    values = payload["can_transform_to"]
    assert isinstance(values, dict)
    return {str(key): sorted(str(item) for item in value) for key, value in sorted(values.items())}
