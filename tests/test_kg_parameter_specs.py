from kg.inmemory_repository import InMemoryKGRepository


def test_inmemory_repo_returns_parameter_specs_for_building_fusion() -> None:
    repo = InMemoryKGRepository()

    specs = repo.get_parameter_specs("algo.fusion.building.v1")
    assert specs, "Expected at least one parameter spec for building fusion."

    # Stable ordering is important for UI display and predictable behavior.
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


def test_inmemory_repo_respects_explicit_empty_parameter_specs_fixture() -> None:
    repo = InMemoryKGRepository(parameter_specs={})
    assert repo.get_parameter_specs("algo.fusion.building.v1") == []


def test_safe_algorithm_parameter_specs_cover_current_adapter_inputs() -> None:
    repo = InMemoryKGRepository()

    building_safe_specs = repo.get_parameter_specs("algo.fusion.building.safe")
    road_safe_specs = repo.get_parameter_specs("algo.fusion.road.safe")

    assert {spec.key for spec in building_safe_specs} == {
        "match_similarity_threshold",
        "one_to_one_min_area_similarity",
        "one_to_one_min_shape_similarity",
        "one_to_one_min_overlap_similarity",
    }
    assert {spec.key for spec in road_safe_specs} == {
        "angle_threshold_deg",
        "snap_tolerance_m",
        "match_buffer_m",
        "max_hausdorff_m",
        "dedupe_buffer_m",
    }


def test_parameter_specs_expose_policy_facing_metadata_without_guessing_unknowns() -> None:
    repo = InMemoryKGRepository()

    match_spec = next(
        spec for spec in repo.get_parameter_specs("algo.fusion.building.v1") if spec.key == "match_similarity_threshold"
    )
    safe_road_spec = next(
        spec for spec in repo.get_parameter_specs("algo.fusion.road.safe") if spec.key == "max_hausdorff_m"
    )

    assert match_spec.tunable is True
    assert "precision" in match_spec.optimization_tags
    assert "recall" in match_spec.optimization_tags
    assert safe_road_spec.tunable is True
    assert "stability" in safe_road_spec.optimization_tags
    assert safe_road_spec.default is not None
