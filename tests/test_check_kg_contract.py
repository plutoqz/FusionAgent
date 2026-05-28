from kg.bootstrap import expected_seed_inventory


def test_expected_seed_inventory_exposes_static_kg_contract() -> None:
    inventory = expected_seed_inventory()

    assert inventory["DataType"] == 27
    assert inventory["Task"] == 11
    assert inventory["TaskBundle"] == 4
    assert inventory["Algorithm"] == 33
    assert inventory["AlgorithmParameterSpec"] == 72
    assert inventory["DataSource"] == 30
    assert inventory["ScenarioProfile"] == 4
    assert inventory["QoSPolicy"] == 4
    assert inventory["OutputSchemaPolicy"] == 5
    assert inventory["OutputRequirement"] == 5
    assert inventory["DataNeed"] == 12
    assert inventory["RepairStrategy"] == 2
    assert inventory["WorkflowPattern"] == 15
