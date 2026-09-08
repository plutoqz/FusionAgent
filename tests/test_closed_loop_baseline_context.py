from services.closed_loop_baseline_context import public_planning_context


def test_public_context_excludes_kg_strategy_and_rankings():
    raw = {
        "intent": {"trigger": {"content": "road", "disaster_type": "flood"}, "secret_policy": "hidden"},
        "retrieval": {
            "candidate_patterns": ["hidden"],
            "algorithms": {
                "a": {
                    "algo_id": "a", "success_rate": 0.9, "input_types": ["road"],
                    "metadata": {"runtime_status": "runtime_candidate", "selectable_now": True},
                },
                "hidden_transform": {
                    "algo_id": "hidden_transform", "input_types": ["raw"],
                    "metadata": {"selectable_now": True},
                },
            },
            "data_sources": [
                {"source_id": "upload.bundle", "source_kind": "local_upload"},
                {"source_id": "catalog", "source_kind": "catalog", "supported_types": ["road"], "ranking_score": 1},
            ],
            "repair_strategies": ["hidden"],
            "parameter_specs": {"a": [{"name": "buffer", "default": 20}]},
        },
        "execution_hints": {"acquisition_observation": {"cache_hit": True}, "ranked_policies": ["hidden"]},
        "output_schema": {"type": "object"},
    }
    public = public_planning_context(raw)
    assert "hidden" not in str(public)
    assert "success_rate" not in str(public)
    assert "hidden_transform" not in public["tools"]["algorithms"]
    assert public["tools"]["algorithms"]["a"]["runtime_status"] == "runtime_candidate"
    assert "ranking_score" not in str(public)
    assert public["tools"]["sources"][0]["source_id"] == "catalog"
    assert len(public["tools"]["sources"]) == 1
    assert public["tools"]["parameter_specs"]["a"][0]["default"] == 20
    public["observations"]["acquisition_observation"]["cache_hit"] = False
    assert raw["execution_hints"]["acquisition_observation"]["cache_hit"] is True
