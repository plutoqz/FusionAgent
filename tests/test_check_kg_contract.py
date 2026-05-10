from kg.bootstrap import expected_seed_inventory


def test_expected_seed_inventory_exposes_static_kg_contract() -> None:
    inventory = expected_seed_inventory()

    assert inventory["DataType"] == 27
    assert inventory["Task"] == 10
    assert inventory["Algorithm"] == 33
    assert inventory["AlgorithmParameterSpec"] == 44
    assert inventory["DataSource"] == 22
    assert inventory["ScenarioProfile"] == 4
    assert inventory["OutputSchemaPolicy"] == 4
    assert inventory["WorkflowPattern"] == 14
