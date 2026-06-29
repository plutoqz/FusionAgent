import json
from pathlib import Path

from kg.inmemory_repository import InMemoryKGRepository
from kg.models import DurableLearningRecord, DurableLearningSummary, ExecutionFeedback
from kg.seed_manifest import build_seed_manifest_payload
from schemas.fusion import JobType


def test_build_context_exposes_task_nodes_and_scenario_profiles() -> None:
    repo = InMemoryKGRepository()

    context = repo.build_context(job_type=JobType.building, disaster_type="flood")

    assert context.task_nodes
    assert any(task.task_id == "task.building.fusion" for task in context.task_nodes)
    assert context.scenario_profiles
    assert any(profile.profile_id == "scenario.flood.default" for profile in context.scenario_profiles)


def test_inmemory_repository_returns_ranked_data_sources() -> None:
    repo = InMemoryKGRepository()

    sources = repo.get_candidate_data_sources(
        job_type=JobType.building,
        disaster_type="flood",
        required_type="dt.building.bundle",
        limit=3,
    )

    assert sources
    assert sources[0].source_id == "upload.bundle"
    assert all("dt.building.bundle" in source.supported_types for source in sources)


def test_inmemory_repository_returns_water_pattern_and_task_driven_bundle_sources() -> None:
    repo = InMemoryKGRepository()

    patterns = repo.get_candidate_patterns(job_type=JobType.water, disaster_type="flood")
    sources = repo.get_candidate_data_sources(
        job_type=JobType.water,
        disaster_type="flood",
        required_type="dt.water.bundle",
    )

    pattern_ids = [pattern.pattern_id for pattern in patterns]
    assert "wp.flood.water.default" in pattern_ids
    assert "wp.waterways.fusioncode.conflation.v7" in pattern_ids
    default_pattern = next(pattern for pattern in patterns if pattern.pattern_id == "wp.flood.water.default")
    assert default_pattern.metadata["input_strategy"] == "task_driven_auto_supported"
    assert default_pattern.metadata["source_family"] == "catalog_water_bundle"
    source_ids = {source.source_id for source in sources}
    assert "upload.bundle" in source_ids
    assert "catalog.flood.water" in source_ids


def test_inmemory_repository_returns_poi_pattern_and_task_driven_bundle_sources() -> None:
    repo = InMemoryKGRepository()

    patterns = repo.get_candidate_patterns(job_type=JobType.poi, disaster_type="generic")
    sources = repo.get_candidate_data_sources(
        job_type=JobType.poi,
        disaster_type="generic",
        required_type="dt.poi.bundle",
    )

    pattern_ids = [pattern.pattern_id for pattern in patterns]
    assert "wp.generic.poi.default" in pattern_ids
    assert "wp.poi.fusioncode.geohash_priority.v1" in pattern_ids
    source_ids = {source.source_id for source in sources}
    assert "upload.bundle" in source_ids
    assert "catalog.generic.poi" in source_ids


def test_execution_feedback_changes_pattern_ranking() -> None:
    repo = InMemoryKGRepository()

    patterns_before = repo.get_candidate_patterns(job_type=JobType.building, disaster_type="flood", limit=3)
    assert patterns_before[0].pattern_id == "wp.flood.building.default"

    repo.record_execution_feedback(
        ExecutionFeedback(
            run_id="run-1",
            job_type=JobType.building,
            disaster_type="flood",
            trigger_type="disaster_event",
            success=True,
            pattern_id="wp.flood.building.safe",
            algorithm_id="algo.fusion.building.safe",
            selected_data_source="upload.bundle",
            repaired=False,
            repair_count=0,
            failure_reason=None,
        )
    )

    patterns_after = repo.get_candidate_patterns(job_type=JobType.building, disaster_type="flood", limit=3)
    assert patterns_after[0].pattern_id == "wp.flood.building.safe"


def test_search_knowledge_returns_algorithm_and_pattern_hits() -> None:
    repo = InMemoryKGRepository()

    hits = repo.search_knowledge("safe building", limit=5)

    assert hits
    assert {hit["kind"] for hit in hits} >= {"algorithm", "pattern"}


def test_repository_exposes_multiple_disaster_specific_pattern_candidates() -> None:
    repo = InMemoryKGRepository()

    building_patterns = repo.get_candidate_patterns(job_type=JobType.building, disaster_type="earthquake", limit=4)
    road_patterns = repo.get_candidate_patterns(job_type=JobType.road, disaster_type="typhoon", limit=4)

    assert len(building_patterns) >= 3
    assert len(road_patterns) >= 3
    assert any(pattern.pattern_id == "wp.earthquake.building.default" for pattern in building_patterns)
    assert any(pattern.pattern_id == "wp.earthquake.building.safe" for pattern in building_patterns)
    assert any(pattern.pattern_id == "wp.typhoon.road.default" for pattern in road_patterns)
    assert any(pattern.pattern_id == "wp.road.fusioncode.conflation.v7" for pattern in road_patterns)


def test_repository_exposes_richer_data_source_signals_for_current_themes() -> None:
    repo = InMemoryKGRepository()

    building_sources = repo.get_candidate_data_sources(
        job_type=JobType.building,
        disaster_type="earthquake",
        required_type="dt.building.bundle",
        limit=4,
    )
    road_sources = repo.get_candidate_data_sources(
        job_type=JobType.road,
        disaster_type="typhoon",
        required_type="dt.road.bundle",
        limit=4,
    )

    building_ids = {source.source_id for source in building_sources}
    road_ids = {source.source_id for source in road_sources}

    assert "catalog.earthquake.building" in building_ids
    assert "catalog.typhoon.road" in road_ids

    earthquake_building = next(source for source in building_sources if source.source_id == "catalog.earthquake.building")
    typhoon_road = next(source for source in road_sources if source.source_id == "catalog.typhoon.road")
    earthquake_road = next(source for source in repo.get_candidate_data_sources(
        job_type=JobType.road,
        disaster_type="earthquake",
        required_type="dt.road.bundle",
        limit=4,
    ) if source.source_id == "catalog.earthquake.road")

    assert earthquake_building.source_kind == "catalog"
    assert earthquake_building.quality_tier == "curated"
    assert earthquake_building.freshness_category == "event_snapshot"
    assert earthquake_building.freshness_hours == 96
    assert earthquake_building.freshness_score == 0.71
    assert earthquake_building.supported_job_types == ["building"]
    assert earthquake_building.supported_geometry_types == ["polygon"]

    assert typhoon_road.source_kind == "catalog"
    assert typhoon_road.quality_tier == "curated"
    assert typhoon_road.freshness_category == "event_snapshot"
    assert typhoon_road.freshness_hours == 48
    assert typhoon_road.supported_job_types == ["road"]
    assert typhoon_road.supported_geometry_types == ["line"]
    assert typhoon_road.metadata["component_source_ids"] == ["raw.osm.road", "raw.microsoft.road"]
    assert earthquake_road.metadata["component_source_ids"] == ["raw.osm.road", "raw.microsoft.road"]


def test_repository_exposes_bundle_and_raw_sources_for_catalog_expansion() -> None:
    repo = InMemoryKGRepository()

    bundle_sources = repo.get_candidate_data_sources(
        job_type=JobType.building,
        disaster_type="flood",
        required_type="dt.building.bundle",
        limit=8,
    )
    raw_sources = repo.get_candidate_data_sources(
        job_type=JobType.building,
        disaster_type="generic",
        required_type="dt.raw.vector",
        limit=32,
    )
    road_bundle_sources = repo.get_candidate_data_sources(
        job_type=JobType.road,
        disaster_type="flood",
        required_type="dt.road.bundle",
        limit=8,
    )
    water_bundle_sources = repo.get_candidate_data_sources(
        job_type=JobType.water,
        disaster_type="flood",
        required_type="dt.water.bundle",
        limit=8,
    )

    bundle_ids = {source.source_id for source in bundle_sources}
    raw_ids = {source.source_id for source in raw_sources}
    road_bundle_ids = {source.source_id for source in road_bundle_sources}
    water_bundle_ids = {source.source_id for source in water_bundle_sources}

    assert "catalog.flood.building" in bundle_ids
    assert "catalog.earthquake.building" in bundle_ids
    assert "catalog.flood.road" in road_bundle_ids
    assert "catalog.flood.water" in water_bundle_ids
    assert "raw.overture.transportation" in raw_ids
    assert "raw.microsoft.road" in raw_ids
    assert "raw.osm.water" in raw_ids
    assert "raw.local.water" in raw_ids
    assert "raw.hydrorivers.water" in raw_ids
    assert "raw.hydrolakes.water" in raw_ids
    assert "raw.osm.poi" in raw_ids
    assert "raw.microsoft.building" in raw_ids
    assert "raw.google.building" in raw_ids
    assert "raw.overture.road" in raw_ids
    assert "raw.hydrorivers.water" in raw_ids
    assert "raw.hydrolakes.water" in raw_ids

    flood_bundle = next(source for source in bundle_sources if source.source_id == "catalog.flood.building")
    assert flood_bundle.metadata["component_source_ids"] == ["raw.osm.building", "raw.microsoft.building"]
    assert flood_bundle.metadata["bundle_strategy"] == "osm_ref_pair"
    road_bundle = next(source for source in road_bundle_sources if source.source_id == "catalog.flood.road")
    assert road_bundle.metadata["component_source_ids"] == ["raw.osm.road", "raw.microsoft.road"]
    assert road_bundle.metadata["bundle_strategy"] == "osm_ref_pair"
    water_bundle = next(source for source in water_bundle_sources if source.source_id == "catalog.flood.water")
    assert water_bundle.metadata["component_source_ids"] == ["raw.osm.water", "raw.hydrolakes.water"]
    assert water_bundle.metadata["bundle_strategy"] == "osm_ref_pair"


def test_repository_exposes_locked_track_b_manual_preload_sources_for_road_and_water() -> None:
    repo = InMemoryKGRepository()

    raw_sources = repo.get_candidate_data_sources(
        job_type=JobType.road,
        disaster_type="generic",
        required_type="dt.raw.vector",
        limit=16,
    )

    by_id = {source.source_id: source for source in raw_sources}

    assert by_id["raw.overture.road"].metadata["acquisition_class"] == "manual_preload_required"
    assert by_id["raw.overture.road"].metadata["runtime_status"] == "reservation_only"
    assert by_id["raw.hydrorivers.water"].metadata["acquisition_class"] == "official_remote_supported"
    assert by_id["raw.hydrorivers.water"].metadata["runtime_status"] == "runtime_candidate"
    assert by_id["raw.hydrolakes.water"].metadata["acquisition_class"] == "official_remote_supported"
    assert by_id["raw.hydrolakes.water"].metadata["runtime_status"] == "runtime_candidate"


def test_repository_exposes_reserved_building_sources_and_raster_inputs() -> None:
    repo = InMemoryKGRepository()

    raw_sources = repo.get_candidate_data_sources(
        job_type=JobType.building,
        disaster_type="generic",
        required_type="dt.raw.vector",
        limit=16,
    )
    raster_sources = repo.get_candidate_data_sources(
        job_type=JobType.building,
        disaster_type="generic",
        required_type="dt.raster.building_presence",
        limit=4,
    )

    raw_ids = {source.source_id for source in raw_sources}
    assert "raw.openbuildingmap.building" in raw_ids
    assert "raw.local.microsoft.building" in raw_ids
    assert "raw.google.open_buildings.vector" in raw_ids

    openbuildingmap = next(source for source in raw_sources if source.source_id == "raw.openbuildingmap.building")
    assert openbuildingmap.metadata["runtime_status"] == "reservation_only"
    assert openbuildingmap.metadata["selectable_now"] is False
    assert openbuildingmap.metadata["height_semantics"] == "estimated_height"

    raster = next(source for source in raster_sources if source.source_id == "raw.google.building_presence.raster")
    assert raster.metadata["runtime_status"] == "reservation_only"
    assert raster.metadata["selectable_now"] is False
    assert raster.metadata["source_form"] == "raster"
    assert raster.metadata["height_semantics"] == "presence_only"


def test_inmemory_repository_persists_and_filters_durable_learning_records() -> None:
    repo = InMemoryKGRepository()

    repo.record_durable_learning_record(
        DurableLearningRecord(
            record_id="dlr-building-success",
            run_id="run-building-success",
            job_type=JobType.building,
            trigger_type="disaster_event",
            success=True,
            disaster_type="flood",
            pattern_id="wp.flood.building.default",
            algorithm_id="algo.fusion.building.v1",
            selected_data_source="upload.bundle",
            output_data_type="dt.building.fused",
            target_crs="EPSG:32643",
            repaired=False,
            repair_count=0,
            plan_revision=1,
            created_at="2026-04-09T01:00:00+00:00",
        )
    )
    repo.record_durable_learning_record(
        DurableLearningRecord(
            record_id="dlr-road-failure",
            run_id="run-road-failure",
            job_type=JobType.road,
            trigger_type="disaster_event",
            success=False,
            disaster_type="flood",
            pattern_id="wp.flood.road.default",
            algorithm_id="algo.fusion.road.conflation.v7",
            selected_data_source="catalog.typhoon.road",
            output_data_type="dt.road.fused",
            target_crs="EPSG:32643",
            repaired=True,
            repair_count=2,
            failure_reason="RuntimeError: still failing",
            plan_revision=2,
            created_at="2026-04-09T02:00:00+00:00",
        )
    )

    building_records = repo.list_durable_learning_records(job_type=JobType.building, limit=5)
    assert [record.record_id for record in building_records] == ["dlr-building-success"]
    assert building_records[0].output_data_type == "dt.building.fused"

    failed_records = repo.list_durable_learning_records(success=False, limit=5)
    assert [record.record_id for record in failed_records] == ["dlr-road-failure"]
    assert failed_records[0].failure_reason == "RuntimeError: still failing"


def test_repository_aggregates_durable_learning_records_for_retrieval() -> None:
    repo = InMemoryKGRepository()

    repo.record_durable_learning_record(
        DurableLearningRecord(
            record_id="dlr-1",
            run_id="run-1",
            job_type=JobType.building,
            trigger_type="disaster_event",
            success=True,
            disaster_type="flood",
            pattern_id="wp.flood.building.default",
            algorithm_id="algo.fusion.building.v1",
            selected_data_source="upload.bundle",
            output_data_type="dt.building.fused",
            target_crs="EPSG:32643",
            repaired=False,
            repair_count=0,
            plan_revision=1,
            created_at="2026-04-09T01:00:00+00:00",
        )
    )
    repo.record_durable_learning_record(
        DurableLearningRecord(
            record_id="dlr-2",
            run_id="run-2",
            job_type=JobType.building,
            trigger_type="disaster_event",
            success=False,
            disaster_type="flood",
            pattern_id="wp.flood.building.default",
            algorithm_id="algo.fusion.building.v1",
            selected_data_source="upload.bundle",
            output_data_type="dt.building.fused",
            target_crs="EPSG:32643",
            repaired=True,
            repair_count=2,
            failure_reason="RuntimeError: failed",
            plan_revision=2,
            created_at="2026-04-09T02:00:00+00:00",
        )
    )

    summary = repo.summarize_durable_learning_records(job_type=JobType.building, disaster_type="flood", limit=5)

    pattern_summary = summary["patterns"][0]
    assert len(summary["patterns"]) == 1
    assert pattern_summary.entity_kind == "pattern"
    assert pattern_summary.entity_id == "wp.flood.building.default"
    assert pattern_summary.job_type == JobType.building
    assert pattern_summary.disaster_type == "flood"
    assert pattern_summary.total_runs == 2
    assert pattern_summary.success_count == 1
    assert pattern_summary.failure_count == 1
    assert pattern_summary.repaired_count == 1
    assert pattern_summary.last_run_at == "2026-04-09T02:00:00+00:00"
    assert pattern_summary.last_failure_reason == "RuntimeError: failed"
    assert summary["algorithms"][0].entity_id == "algo.fusion.building.v1"
    assert summary["data_sources"][0].entity_id == "upload.bundle"


def test_durable_learning_summary_exposes_policy_feedback_fields() -> None:
    summary = DurableLearningSummary(
        entity_kind="pattern",
        entity_id="wp.building",
        job_type=JobType.building,
        disaster_type="flood",
        condition_key="building|flood|small_city",
        time_decayed_score=0.75,
        quality_gate_pass_rate=1.0,
        avg_latency_seconds=12.5,
        recent_success_rate=0.8,
        trend="stable",
        adjustment=0.06,
    )

    assert summary.condition_key == "building|flood|small_city"
    assert summary.adjustment == 0.06
    assert summary.trend == "stable"


def test_durable_learning_summary_uses_condition_key_and_time_decay() -> None:
    repo = InMemoryKGRepository()
    repo.record_durable_learning_record(
        DurableLearningRecord(
            record_id="old-failure",
            run_id="old",
            job_type=JobType.building,
            trigger_type="user_query",
            success=False,
            disaster_type="flood",
            pattern_id="wp.building",
            selected_data_source="raw.osm.building",
            metadata={"aoi_class": "small_city", "region_group": "africa"},
            created_at="2026-05-01T00:00:00+00:00",
        )
    )
    repo.record_durable_learning_record(
        DurableLearningRecord(
            record_id="new-success",
            run_id="new",
            job_type=JobType.building,
            trigger_type="user_query",
            success=True,
            disaster_type="flood",
            pattern_id="wp.building",
            selected_data_source="raw.osm.building",
            metadata={"aoi_class": "small_city", "region_group": "africa"},
            created_at="2026-06-01T00:00:00+00:00",
        )
    )

    summary = repo.summarize_durable_learning_records(
        job_type=JobType.building,
        disaster_type="flood",
        limit=5,
    )["patterns"][0]

    assert summary.condition_key == (
        "task=building|entity=wp.building|aoi=small_city|"
        "source_coverage=unknown|failure=none|quality=unknown"
    )
    assert 0.0 < summary.time_decayed_score <= 1.0
    assert summary.recent_success_rate == 0.5


def test_durable_learning_summary_aggregates_quality_and_latency_metadata() -> None:
    repo = InMemoryKGRepository()
    for record_id, accepted, latency in [
        ("dlr-quality-pass", True, 10.0),
        ("dlr-quality-fail", False, 20.0),
    ]:
        repo.record_durable_learning_record(
            DurableLearningRecord(
                record_id=record_id,
                run_id=record_id.replace("dlr", "run"),
                job_type=JobType.building,
                trigger_type="user_query",
                success=accepted,
                disaster_type="flood",
                pattern_id="wp.quality",
                metadata={
                    "quality_gate_accepted": accepted,
                    "latency_seconds": latency,
                    "aoi_class": "small_city",
                    "region_group": "africa",
                },
                created_at=f"2026-06-01T00:00:{int(latency):02d}+00:00",
            )
        )

    summary = repo.summarize_durable_learning_records(
        job_type=JobType.building,
        disaster_type="flood",
        limit=5,
    )["patterns"][0]

    assert summary.quality_gate_pass_rate == 0.5
    assert summary.avg_latency_seconds == 15.0


def test_inmemory_repository_can_load_seed_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "seed.json"
    manifest_path.write_text(
        json.dumps(build_seed_manifest_payload(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    repo = InMemoryKGRepository(seed_manifest_path=manifest_path)

    assert repo.get_algorithm("algo.fusion.building.v1") is not None
    assert repo.get_candidate_patterns(job_type=JobType.building, disaster_type="flood")
