from __future__ import annotations

from pathlib import Path

from schemas.settings import EffectiveLLMSettings
from services.agent_run_service import AgentRunService


def test_agent_run_service_refresh_runtime_dependencies_rebuilds_planner_and_executor(
    tmp_path: Path, monkeypatch
) -> None:
    planner_instances: list[object] = []
    executor_instances: list[object] = []
    initial_provider = object()
    refreshed_provider = object()
    create_provider_calls: list[object] = []

    class FakePlanner:
        def __init__(self, kg_repo, llm_provider, artifact_registry=None) -> None:
            self.kg_repo = kg_repo
            self.llm_provider = llm_provider
            self.artifact_registry = artifact_registry
            planner_instances.append(self)

    class FakeExecutor:
        def __init__(self, kg_repo, planner=None, algorithm_handlers=None, tool_registry=None) -> None:
            self.kg_repo = kg_repo
            self.planner = planner
            executor_instances.append(self)

    def fake_create_llm_provider(settings=None):
        create_provider_calls.append(settings)
        if settings is None:
            return initial_provider
        return refreshed_provider

    monkeypatch.setattr("services.agent_run_service.create_llm_provider", fake_create_llm_provider)
    monkeypatch.setattr("services.agent_run_service.WorkflowPlanner", FakePlanner)
    monkeypatch.setattr("services.agent_run_service.WorkflowExecutor", FakeExecutor)
    monkeypatch.setattr("services.agent_run_service.AgentRunService._build_geocoder", lambda self: object())
    monkeypatch.setattr("services.agent_run_service.AgentRunService._build_raw_vector_source_service", lambda self: object())
    monkeypatch.setattr("services.agent_run_service.AgentRunService._build_input_bundle_providers", lambda self: [])

    kg_repo = object()
    service = AgentRunService(base_dir=tmp_path / "runs", kg_repo=kg_repo)

    assert service.llm_provider is initial_provider
    assert service.planner is planner_instances[0]
    assert service.planner.llm_provider is initial_provider
    assert service.executor is executor_instances[0]
    assert service.executor.planner is service.planner

    effective_settings = EffectiveLLMSettings(
        provider="openai",
        base_url="https://runtime.example/v1",
        api_key="sk-runtime-secret",
        model="gpt-runtime",
        timeout_sec=33,
    )

    service.refresh_runtime_dependencies(effective_settings)

    assert create_provider_calls == [None, effective_settings]
    assert service.llm_provider is refreshed_provider
    assert len(planner_instances) == 2
    assert service.planner is planner_instances[-1]
    assert service.planner.kg_repo is kg_repo
    assert service.planner.llm_provider is refreshed_provider
    assert service.planner.artifact_registry is service.artifact_registry
    assert len(executor_instances) == 2
    assert service.executor is executor_instances[-1]
    assert service.executor.kg_repo is kg_repo
    assert service.executor.planner is service.planner
