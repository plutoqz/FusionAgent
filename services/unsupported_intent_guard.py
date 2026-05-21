from __future__ import annotations

from typing import Any


UNSUPPORTED_INTENT_RULES = [
    {
        "code": "trajectory_to_road_deferred",
        "message": "trajectory-to-road is reservation-only in this phase",
        "keywords": ("trajectory", "gps trace", "gps trajectory", "轨迹", "轨迹到道路"),
        "job_types": ("road",),
    },
    {
        "code": "UNBOUNDED_POI_ENTITY_ALIGNMENT",
        "message": "POI fusion is bounded and does not support open-ended entity alignment.",
        "keywords": (
            "entity resolution",
            "entity alignment",
            "all businesses",
            "all poi businesses",
            "global entity",
            "通用实体对齐",
        ),
        "job_types": ("poi",),
    },
    {
        "code": "OFF_DOMAIN_REQUEST",
        "message": "Request includes off-domain content that the fusion workflow does not support.",
        "keywords": (
            "gdp",
            "gross domestic product",
            "population heatmap",
            "stock market",
            "国内生产总值",
            "人口热力",
            "人口",
        ),
        "job_types": ("building", "road", "water", "poi"),
    },
    {
        "code": "UNSUPPORTED_OUTPUT_SCHEMA_CUSTOMIZATION",
        "message": "Request asks for output schema customization that is not supported.",
        "keywords": (
            "列名改成中文",
            "中文列名",
            "属性表列名",
            "rename all columns",
            "rename columns",
            "custom output schema",
            "schema customization",
        ),
        "job_types": ("building", "road", "water", "poi"),
    },
]


def _job_type_value(job_type: Any) -> str:
    return str(getattr(job_type, "value", job_type))


def classify_unsupported_intent(content: str, *, job_type: str) -> list[dict[str, str]]:
    normalized = str(content or "").casefold()
    normalized_job_type = _job_type_value(job_type).casefold()
    for rule in UNSUPPORTED_INTENT_RULES:
        if normalized_job_type not in rule["job_types"]:
            continue
        for keyword in rule["keywords"]:
            if keyword.casefold() in normalized:
                return [
                    {
                        "code": rule["code"],
                        "message": rule["message"],
                        "matched_keyword": keyword,
                        "job_type": normalized_job_type,
                    }
                ]
    return []
