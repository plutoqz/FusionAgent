from __future__ import annotations

from typing import Dict

from kg.knowledge_release import KnowledgeReleaseError
from kg.policy_registry import KnowledgePolicyRegistry, default_policy_registry
from schemas.agent import RunTrigger


def resolve_planning_mode(
    trigger: RunTrigger,
    *,
    policy_registry: KnowledgePolicyRegistry | None = None,
) -> Dict[str, object]:
    registry = policy_registry or default_policy_registry()
    explicit_disaster = str(trigger.disaster_type or "").strip()
    if explicit_disaster:
        if registry.resolve_disaster_type(explicit_disaster) is None:
            raise KnowledgeReleaseError(
                f"Disaster type is outside the frozen KG vocabulary: {explicit_disaster}"
            )
        return {"planning_mode": "scenario_driven", "profile_source": "disaster_type"}

    task_kinds = registry.task_kinds_in_text(trigger.content or "")
    return {
        "planning_mode": "task_driven",
        "profile_source": "direct_task" if task_kinds else "default_task",
    }
