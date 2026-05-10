from kg.seed import (
    ALGORITHMS,
    DATA_SOURCES,
    DATA_TYPES,
    OUTPUT_SCHEMA_POLICIES,
    PARAMETER_SPECS,
    SCENARIO_PROFILES,
    TASKS,
    WORKFLOW_PATTERNS,
)


def test_seed_inventory_matches_expected_static_counts() -> None:
    assert len(DATA_TYPES) == 27
    assert len(TASKS) == 10
    assert len(ALGORITHMS) == 33
    assert sum(len(items) for items in PARAMETER_SPECS.values()) == 44
    assert len(DATA_SOURCES) == 22
    assert len(SCENARIO_PROFILES) == 4
    assert len(OUTPUT_SCHEMA_POLICIES) == 4
    assert len(WORKFLOW_PATTERNS) == 14
