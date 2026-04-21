from kg.inmemory_repository import InMemoryKGRepository
from kg.seed import (
    ALGORITHMS,
    CAN_TRANSFORM_TO,
    DATA_SOURCES,
    DATA_TYPES,
    OUTPUT_SCHEMA_POLICIES,
    TASKS,
    WORKFLOW_PATTERNS,
)
from schemas.fusion import JobType


def test_kg_context_exposes_seeded_data_types() -> None:
    context = InMemoryKGRepository().build_context(job_type=JobType.building, disaster_type="flood")

    exposed = {item.type_id for item in context.data_types}

    assert "dt.building.bundle" in exposed
    assert "dt.building.fused" in exposed
    assert set(DATA_TYPES).issubset(exposed)


def test_seed_ontology_data_type_references_are_closed() -> None:
    known = set(DATA_TYPES)
    missing: list[str] = []

    for algorithm in ALGORITHMS.values():
        for type_id in [*algorithm.input_types, algorithm.output_type]:
            if type_id not in known:
                missing.append(f"algorithm:{algorithm.algo_id}:{type_id}")

    for source in DATA_SOURCES:
        for type_id in source.supported_types:
            if type_id not in known:
                missing.append(f"source:{source.source_id}:{type_id}")

    for pattern in WORKFLOW_PATTERNS:
        for step in pattern.steps:
            for type_id in [step.input_data_type, step.output_data_type]:
                if type_id not in known:
                    missing.append(f"pattern:{pattern.pattern_id}:{type_id}")

    for policy in OUTPUT_SCHEMA_POLICIES.values():
        if policy.output_type not in known:
            missing.append(f"schema_policy:{policy.policy_id}:{policy.output_type}")

    for from_type, to_types in CAN_TRANSFORM_TO.items():
        if from_type not in known:
            missing.append(f"transform:from:{from_type}")
        for to_type in to_types:
            if to_type not in known:
                missing.append(f"transform:to:{to_type}")

    assert missing == []


def test_water_seed_records_exist() -> None:
    assert "dt.water.bundle" in DATA_TYPES
    assert "dt.water.fused" in DATA_TYPES
    assert "task.water.fusion" in TASKS
    assert "algo.fusion.water.v1" in ALGORITHMS
    assert OUTPUT_SCHEMA_POLICIES["dt.water.fused"].policy_id == "osp.water.fused.v1"
    water_pattern = next(pattern for pattern in WORKFLOW_PATTERNS if pattern.job_type == JobType.water)
    assert water_pattern.metadata["input_strategy"] == "task_driven_auto_supported"
    assert water_pattern.metadata["source_family"] == "catalog_water_bundle"
    water_source = next(source for source in DATA_SOURCES if source.source_id == "catalog.flood.water")
    assert water_source.supported_types == ["dt.water.bundle"]
    assert water_source.metadata["component_source_ids"] == ["raw.osm.water", "raw.local.water"]
    water_policy_note = OUTPUT_SCHEMA_POLICIES["dt.water.fused"].metadata["notes"]
    assert "uploaded-only" not in water_policy_note
    assert "shared bundle runtime" in water_policy_note
