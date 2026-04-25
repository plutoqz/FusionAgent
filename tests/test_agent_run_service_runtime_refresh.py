from __future__ import annotations

from pathlib import Path

import pytest

from schemas.agent import RunArtifactMeta, RunCreateRequest, RunInputStrategy, RunTrigger, RunTriggerType, WorkflowPlan
from schemas.fusion import JobType
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


def test_execute_run_uses_bound_runtime_snapshot_after_refresh_for_queued_run(tmp_path: Path, monkeypatch) -> None:
    planner_instances: list[object] = []
    executor_instances: list[object] = []
    create_provider_calls: list[object] = []
    captured_runtime_providers: list[str | None] = []
    initial_provider = object()
    refreshed_provider = object()

    class FakePlanner:
        def __init__(self, kg_repo, llm_provider, artifact_registry=None) -> None:
            self.kg_repo = kg_repo
            self.llm_provider = llm_provider
            self.artifact_registry = artifact_registry
            self.context_builder = type("ContextBuilder", (), {"resolved_aoi_override": None})()
            planner_instances.append(self)

    class FakeExecutor:
        def __init__(self, kg_repo, planner=None, algorithm_handlers=None, tool_registry=None) -> None:
            self.kg_repo = kg_repo
            self.planner = planner
            executor_instances.append(self)

    def fake_create_llm_provider(settings=None):
        create_provider_calls.append(settings)
        if settings is None or settings.provider == "mock":
            return initial_provider
        return refreshed_provider

    monkeypatch.setattr("services.agent_run_service.create_llm_provider", fake_create_llm_provider)
    monkeypatch.setattr("services.agent_run_service.WorkflowPlanner", FakePlanner)
    monkeypatch.setattr("services.agent_run_service.WorkflowExecutor", FakeExecutor)
    monkeypatch.setattr("services.agent_run_service.AgentRunService._build_geocoder", lambda self: object())
    monkeypatch.setattr("services.agent_run_service.AgentRunService._build_raw_vector_source_service", lambda self: object())
    monkeypatch.setattr("services.agent_run_service.AgentRunService._build_input_bundle_providers", lambda self: [])

    service = AgentRunService(base_dir=tmp_path / "runs", kg_repo=object())
    service.dispatch_eager = False
    monkeypatch.setattr(service, "_dispatch_run", lambda *args, **kwargs: None)

    request = RunCreateRequest(
        job_type=JobType.building,
        trigger=RunTrigger(type=RunTriggerType.user_query, content="building"),
        target_crs="EPSG:4326",
        field_mapping={},
        debug=False,
        input_strategy=RunInputStrategy.uploaded,
    )

    status = service.create_run(
        request=request,
        osm_zip_name="osm.zip",
        osm_zip_bytes=b"osm",
        ref_zip_name="ref.zip",
        ref_zip_bytes=b"ref",
    )

    refreshed_settings = EffectiveLLMSettings(
        provider="openai",
        base_url="https://runtime.example/v1",
        api_key="sk-runtime-secret",
        model="gpt-runtime",
        timeout_sec=33,
    )
    service.refresh_runtime_dependencies(refreshed_settings)

    def fake_run_planning_stage(run_id: str, request: RunCreateRequest, runtime_dependencies=None) -> WorkflowPlan:
        captured_runtime_providers.append(runtime_dependencies.settings.provider if runtime_dependencies else None)
        return WorkflowPlan.model_validate(
            {
                "workflow_id": "wf_runtime_snapshot",
                "trigger": request.trigger.model_dump(mode="json"),
                "context": {"plan_revision": 1},
                "tasks": [],
                "expected_output": "snapshot",
            }
        )

    def fake_run_validation_stage(run_id: str, plan: WorkflowPlan) -> WorkflowPlan:
        return plan

    def fake_run_execution_stage(
        run_id: str,
        request: RunCreateRequest,
        plan: WorkflowPlan,
        osm_zip_path: Path,
        ref_zip_path: Path,
        intermediate_dir: Path,
        output_dir: Path,
        repair_records=None,
        runtime_dependencies=None,
    ):
        captured_runtime_providers.append(runtime_dependencies.settings.provider if runtime_dependencies else None)
        fused = output_dir / "fused.shp"
        output_dir.mkdir(parents=True, exist_ok=True)
        fused.write_text("ok", encoding="utf-8")
        return fused, []

    monkeypatch.setattr(service, "run_planning_stage", fake_run_planning_stage)
    monkeypatch.setattr(service, "run_validation_stage", fake_run_validation_stage)
    monkeypatch.setattr(service, "_attempt_artifact_reuse", lambda **kwargs: None)
    monkeypatch.setattr(
        service,
        "_resolve_execution_inputs",
        lambda **kwargs: (kwargs["osm_zip_path"], kwargs["ref_zip_path"], None),
    )
    monkeypatch.setattr(service, "run_execution_stage", fake_run_execution_stage)
    monkeypatch.setattr(
        service,
        "run_writeback_stage",
        lambda **kwargs: RunArtifactMeta(filename="artifact.zip", path=str(kwargs["output_dir"] / "artifact.zip"), size_bytes=1),
    )

    run_dir = service.base_dir / status.run_id
    service.execute_run(
        run_id=status.run_id,
        request=request,
        osm_zip_path=run_dir / "input" / "osm.zip",
        ref_zip_path=run_dir / "input" / "ref.zip",
        intermediate_dir=run_dir / "intermediate",
        output_dir=run_dir / "output",
        log_dir=run_dir / "logs",
    )

    assert create_provider_calls[0] is None
    assert create_provider_calls[1] == refreshed_settings
    assert create_provider_calls[2] == EffectiveLLMSettings(provider="mock")
    assert captured_runtime_providers == ["mock", "mock"]
    assert service.planner is planner_instances[1]
    assert service.planner.llm_provider is refreshed_provider
    assert service.executor is executor_instances[1]
    assert service.executor.planner is service.planner


def test_refresh_runtime_dependencies_raises_and_keeps_current_default_runtime(tmp_path: Path, monkeypatch) -> None:
    initial_provider = object()

    class FakePlanner:
        def __init__(self, kg_repo, llm_provider, artifact_registry=None) -> None:
            self.llm_provider = llm_provider
            self.artifact_registry = artifact_registry

    class FakeExecutor:
        def __init__(self, kg_repo, planner=None, algorithm_handlers=None, tool_registry=None) -> None:
            self.planner = planner

    def fake_create_llm_provider(settings=None):
        if settings is None:
            return initial_provider
        raise RuntimeError("api_key is required for openai provider.")

    monkeypatch.setattr("services.agent_run_service.create_llm_provider", fake_create_llm_provider)
    monkeypatch.setattr("services.agent_run_service.WorkflowPlanner", FakePlanner)
    monkeypatch.setattr("services.agent_run_service.WorkflowExecutor", FakeExecutor)
    monkeypatch.setattr("services.agent_run_service.AgentRunService._build_geocoder", lambda self: object())
    monkeypatch.setattr("services.agent_run_service.AgentRunService._build_raw_vector_source_service", lambda self: object())
    monkeypatch.setattr("services.agent_run_service.AgentRunService._build_input_bundle_providers", lambda self: [])

    service = AgentRunService(base_dir=tmp_path / "runs", kg_repo=object())
    original_planner = service.planner
    original_executor = service.executor

    with pytest.raises(RuntimeError, match="api_key is required"):
        service.refresh_runtime_dependencies(
            EffectiveLLMSettings(
                provider="openai",
                base_url="https://runtime.example/v1",
                model="gpt-runtime",
                timeout_sec=33,
            )
        )

    assert service.llm_provider is initial_provider
    assert service.planner is original_planner
    assert service.executor is original_executor
