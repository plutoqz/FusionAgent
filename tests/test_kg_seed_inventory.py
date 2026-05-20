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


def test_seed_inventory_matches_expected_static_counts() -> None:
    assert len(DATA_TYPES) == 27
    assert len(TASKS) == 10
    assert len(TASK_BUNDLES) == 4
    assert len(ALGORITHMS) == 33
    assert sum(len(items) for items in PARAMETER_SPECS.values()) == 44
    assert len(DATA_SOURCES) == 26
    assert len(SCENARIO_PROFILES) == 4
    assert len(QOS_POLICIES) == 4
    assert len(OUTPUT_SCHEMA_POLICIES) == 4
    assert len(OUTPUT_REQUIREMENTS) == 4
    assert len(DATA_NEEDS) == 10
    assert len(REPAIR_STRATEGIES) == 2
    assert len(WORKFLOW_PATTERNS) == 14
