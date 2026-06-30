from kg.seed import (
    ALGORITHMS,
    DATA_NEEDS,
    DATA_SOURCES,
    DATA_TYPES,
    OUTPUT_SCHEMA_POLICIES,
    OUTPUT_REQUIREMENTS,
    PARAMETER_SPECS,
    QOS_POLICIES,
    REPAIR_STRATEGIES,
    SCENARIO_PROFILES,
    TASK_BUNDLES,
    TASKS,
    WORKFLOW_PATTERNS,
)
from kg.seed_provider import load_seed_data


def test_seed_inventory_matches_expected_static_counts() -> None:
    assert len(DATA_TYPES) == 27
    assert len(TASKS) == 11
    assert len(TASK_BUNDLES) == 4
    assert len(ALGORITHMS) == 33
    assert sum(len(items) for items in PARAMETER_SPECS.values()) == 72
    assert len(DATA_SOURCES) == 32
    assert len(SCENARIO_PROFILES) == 4
    assert len(QOS_POLICIES) == 4
    assert len(OUTPUT_SCHEMA_POLICIES) == 5
    assert len(OUTPUT_REQUIREMENTS) == 5
    assert len(DATA_NEEDS) == 12
    assert len(REPAIR_STRATEGIES) == 2
    assert len(WORKFLOW_PATTERNS) == 15


def test_default_seed_provider_matches_current_seed_inventory() -> None:
    payload = load_seed_data()

    assert len(payload["data_types"]) == len(DATA_TYPES)
    assert len(payload["algorithms"]) == len(ALGORITHMS)
    assert sum(len(items) for items in payload["parameter_specs"].values()) == sum(
        len(items) for items in PARAMETER_SPECS.values()
    )
    assert len(payload["patterns"]) == len(WORKFLOW_PATTERNS)
    assert len(payload["data_sources"]) == len(DATA_SOURCES)
    assert len(payload["output_schema_policies"]) == len(OUTPUT_SCHEMA_POLICIES)

    assert set(payload["data_types"]) == set(DATA_TYPES)
    assert set(payload["algorithms"]) == set(ALGORITHMS)
    assert set(payload["parameter_specs"]) == set(PARAMETER_SPECS)
    assert {item.pattern_id for item in payload["patterns"]} == {
        item.pattern_id for item in WORKFLOW_PATTERNS
    }
    assert {item.source_id for item in payload["data_sources"]} == {
        item.source_id for item in DATA_SOURCES
    }
    assert set(payload["output_schema_policies"]) == set(OUTPUT_SCHEMA_POLICIES)
