from __future__ import annotations

import importlib
import importlib.util


def _load_guard_module():
    spec = importlib.util.find_spec("services.unsupported_intent_guard")
    assert spec is not None, "services.unsupported_intent_guard module must exist"
    return importlib.import_module("services.unsupported_intent_guard")


def test_classify_unsupported_intent_flags_off_domain_request() -> None:
    module = _load_guard_module()

    issues = module.classify_unsupported_intent(
        "请融合建筑数据，同时给我某国家GDP数据",
        job_type="building",
    )

    assert issues == [
        {
            "code": "OFF_DOMAIN_REQUEST",
            "message": "Request includes off-domain content that the fusion workflow does not support.",
            "matched_keyword": "gdp",
            "job_type": "building",
        }
    ]


def test_classify_unsupported_intent_flags_schema_customization_request() -> None:
    module = _load_guard_module()

    issues = module.classify_unsupported_intent(
        "请把融合后属性表列名改成中文",
        job_type="building",
    )

    assert issues == [
        {
            "code": "UNSUPPORTED_OUTPUT_SCHEMA_CUSTOMIZATION",
            "message": "Request asks for output schema customization that is not supported.",
            "matched_keyword": "列名改成中文",
            "job_type": "building",
        }
    ]


def test_classify_unsupported_intent_allows_normal_building_request() -> None:
    module = _load_guard_module()

    issues = module.classify_unsupported_intent(
        "need building data for Nairobi",
        job_type="building",
    )

    assert issues == []


def test_classify_unsupported_intent_flags_trajectory_to_road_execution_request() -> None:
    module = _load_guard_module()

    issues = module.classify_unsupported_intent(
        "please ingest GPS trajectory and build a road network",
        job_type="road",
    )

    assert issues == [
        {
            "code": "trajectory_to_road_deferred",
            "message": "trajectory-to-road is reservation-only in this phase",
            "matched_keyword": "trajectory",
            "job_type": "road",
        }
    ]


def test_classify_unsupported_intent_flags_unbounded_poi_entity_alignment() -> None:
    module = _load_guard_module()

    issues = module.classify_unsupported_intent(
        "merge all POI businesses and solve global entity resolution",
        job_type="poi",
    )

    assert issues == [
        {
            "code": "UNBOUNDED_POI_ENTITY_ALIGNMENT",
            "message": "POI fusion is bounded and does not support open-ended entity alignment.",
            "matched_keyword": "entity resolution",
            "job_type": "poi",
        }
    ]
