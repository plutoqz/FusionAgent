from __future__ import annotations

from typing import Dict

from schemas.agent import RunTrigger


TASK_HINTS = (
    "need",
    "download",
    "data",
    "building",
    "road",
    "water",
    "lake",
    "river",
    "reservoir",
    "pond",
    "gilgit",
    "pakistan",
)

WATER_HINTS = (
    "water",
    "lake",
    "river",
    "reservoir",
    "pond",
    "wetland",
)


def _has_direct_water_request(content: str) -> bool:
    return any(token in content for token in WATER_HINTS)


def resolve_planning_mode(trigger: RunTrigger) -> Dict[str, object]:
    content = (trigger.content or "").lower()
    if trigger.disaster_type:
        return {"planning_mode": "scenario_driven", "profile_source": "disaster_type"}
    if _has_direct_water_request(content):
        return {"planning_mode": "task_driven", "profile_source": "direct_task"}
    if any(token in content for token in TASK_HINTS):
        return {"planning_mode": "task_driven", "profile_source": "direct_task"}
    return {"planning_mode": "task_driven", "profile_source": "default_task"}
