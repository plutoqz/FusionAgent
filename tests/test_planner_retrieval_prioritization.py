from __future__ import annotations

from typing import Any, Dict

from agent.planner import WorkflowPlanner
from agent.retriever import rank_retrieval_candidates
from kg.inmemory_repository import InMemoryKGRepository
from llm.providers.base import LLMProvider
from schemas.fusion import JobType
from schemas.agent import RunTrigger, RunTriggerType


class _CapturingProvider(LLMProvider):
    def __init__(self) -> None:
        self.last_context: Dict[str, Any] | None = None
        self.model = "capturing-model"

    def generate_workflow_plan(self, system_prompt: str, context: Dict[str, Any]) -> Dict[str, Any]:
        self.last_context = context
        self.last_usage = {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14}
        self.last_model = "capturing-plan-model"
        candidate = context["retrieval"]["candidate_patterns"][0]
        first_step = candidate["steps"][0]
        return {
            "workflow_id": "wf_ranked_context",
            "trigger": context["intent"]["trigger"],
            "context": {"legacy": "llm"},
            "tasks": [
                {
                    "step": 1,
                    "name": first_step["name"],
                    "description": "execute selected workflow",
                    "algorithm_id": first_step["algorithm_id"],
                    "input": {
                        "data_type_id": first_step["input_data_type"],
                        "data_source_id": first_step["data_source_id"],
                        "parameters": {},
                    },
                    "output": {
                        "data_type_id": first_step["output_data_type"],
                        "description": "selected output",
                    },
                    "depends_on": [],
                    "is_transform": False,
                    "kg_validated": False,
                    "alternatives": [],
                }
            ],
            "expected_output": "building fused shapefile",
            "estimated_time": "5m",
        }


def test_rank_retrieval_candidates_prefers_better_grounded_sources_and_algorithms() -> None:
    grounded_candidate = {
        "candidate_id": "grounded",
        "source_quality": 1.0,
        "algorithm_fit": 1.0,
        "workflow_support": 1.0,
        "missing_requirements": [],
    }
    weak_candidate = {
        "candidate_id": "weak",
        "source_quality": 0.2,
        "algorithm_fit": 0.3,
        "workflow_support": 0.1,
        "missing_requirements": ["missing_schema"],
    }

    ranked = rank_retrieval_candidates([weak_candidate, grounded_candidate])

    assert ranked[0]["candidate_id"] == "grounded"
    assert ranked[0]["ranking_score"] > ranked[1]["ranking_score"]
    assert ranked[0]["ranking_rationale"] == {
        "source_quality": 1.0,
        "algorithm_fit": 1.0,
        "workflow_support": 1.0,
        "penalty_for_missing_requirements": 0.0,
    }


def test_planner_context_exposes_ranked_retrieval_candidates_and_rationale() -> None:
    provider = _CapturingProvider()
    planner = WorkflowPlanner(InMemoryKGRepository(), provider)
    trigger = RunTrigger(
        type=RunTriggerType.user_query,
        content="need building data for Benin",
    )

    _plan = planner.create_plan(run_id="run-ranked-retrieval", job_type=JobType.building, trigger=trigger)

    assert provider.last_context is not None
    retrieval = provider.last_context["retrieval"]
    patterns = retrieval["candidate_patterns"]
    sources = retrieval["data_sources"]

    assert patterns[0]["pattern_id"] == "wp.flood.building.default"
    assert all("ranking_score" in item for item in patterns)
    assert all("ranking_rationale" in item for item in patterns)
    assert [item["ranking_score"] for item in patterns] == sorted(
        [item["ranking_score"] for item in patterns],
        reverse=True,
    )

    assert all("ranking_score" in item for item in sources)
    assert all("ranking_rationale" in item for item in sources)
    assert [item["ranking_score"] for item in sources] == sorted(
        [item["ranking_score"] for item in sources],
        reverse=True,
    )

    runtime_candidate = next(item for item in sources if item["source_id"] == "catalog.earthquake.building")
    reserved_source = next(item for item in sources if item["source_id"] == "raw.openbuildingmap.building")
    assert runtime_candidate["ranking_score"] > reserved_source["ranking_score"]
    assert set(runtime_candidate["ranking_rationale"]) == {
        "source_quality",
        "algorithm_fit",
        "workflow_support",
        "penalty_for_missing_requirements",
    }

