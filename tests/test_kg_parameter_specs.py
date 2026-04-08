from kg.inmemory_repository import InMemoryKGRepository


def test_inmemory_repo_returns_parameter_specs_for_building_fusion() -> None:
    repo = InMemoryKGRepository()

    specs = repo.get_parameter_specs("algo.fusion.building.v1")
    assert specs, "Expected at least one parameter spec for building fusion."

    orders = [spec.order for spec in specs]
    assert orders == sorted(orders)

    keys = [spec.key for spec in specs]
    assert "match_similarity_threshold" in keys

    match_spec = next(spec for spec in specs if spec.key == "match_similarity_threshold")
    assert match_spec.label
    assert match_spec.param_type == "float"
    assert match_spec.default is not None
    assert match_spec.min_value is not None
    assert match_spec.max_value is not None
    assert float(match_spec.min_value) <= float(match_spec.default) <= float(match_spec.max_value)
    assert match_spec.description


def test_inmemory_repo_returns_parameter_specs_for_road_fusion() -> None:
    repo = InMemoryKGRepository()

    specs = repo.get_parameter_specs("algo.fusion.road.v1")
    assert specs, "Expected at least one parameter spec for road fusion."

    keys = [spec.key for spec in specs]
    assert "angle_threshold_deg" in keys
    assert "max_hausdorff_m" in keys


def test_inmemory_repo_returns_parameter_specs_for_safe_algorithms() -> None:
    repo = InMemoryKGRepository()

    building_safe_keys = {spec.key for spec in repo.get_parameter_specs("algo.fusion.building.safe")}
    road_safe_keys = {spec.key for spec in repo.get_parameter_specs("algo.fusion.road.safe")}

    assert "match_similarity_threshold" in building_safe_keys
    assert "one_to_one_min_overlap_similarity" in building_safe_keys
    assert "max_hausdorff_m" in road_safe_keys
    assert "dedupe_buffer_m" in road_safe_keys


def test_inmemory_repo_respects_explicit_empty_parameter_specs_fixture() -> None:
    repo = InMemoryKGRepository(parameter_specs={})
    assert repo.get_parameter_specs("algo.fusion.building.v1") == []
