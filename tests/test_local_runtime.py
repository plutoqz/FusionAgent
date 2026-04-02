from __future__ import annotations

import os
from pathlib import Path

import pytest

from utils.local_runtime import (
    DependencyConfigError,
    apply_local_dependency_defaults,
    apply_runtime_entrypoint_defaults,
    find_missing_runtime_dependencies,
    read_local_dependency_config,
)


MANAGED_ENV_KEYS = [
    "GEOFUSION_KG_BACKEND",
    "GEOFUSION_NEO4J_URI",
    "GEOFUSION_NEO4J_USER",
    "GEOFUSION_NEO4J_PASSWORD",
    "GEOFUSION_NEO4J_DATABASE",
    "GEOFUSION_CELERY_BROKER",
    "GEOFUSION_CELERY_BACKEND",
    "GEOFUSION_LLM_PROVIDER",
    "GEOFUSION_LLM_BASE_URL",
    "GEOFUSION_LLM_API_KEY",
    "GEOFUSION_LLM_MODEL",
]


@pytest.fixture(autouse=True)
def restore_managed_env() -> None:
    snapshot = {key: os.environ.get(key) for key in MANAGED_ENV_KEYS}
    yield
    for key, value in snapshot.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_read_local_dependency_config_maps_dependency_txt_fields(tmp_path: Path) -> None:
    dependency_file = tmp_path / "依赖.txt"
    dependency_file.write_text(
        "\n".join(
            [
                "Redis端口:6380",
                "",
                "Neo4j用户名:neo4j",
                "Neo4j密码:systemneo4j",
                "",
                "api-key:sk-test",
                'base_url="https://www.dmxapi.cn/v1"',
            ]
        ),
        encoding="utf-8",
    )

    config = read_local_dependency_config(dependency_file)

    assert config.redis_port == 6380
    assert config.neo4j_user == "neo4j"
    assert config.neo4j_password == "systemneo4j"
    assert config.llm_api_key == "sk-test"
    assert config.llm_base_url == "https://www.dmxapi.cn/v1"
    assert config.llm_model == "qwen3.5-397b-a17b"
    assert config.as_env_defaults()["GEOFUSION_CELERY_BROKER"] == "redis://localhost:6380/0"
    assert config.as_env_defaults()["GEOFUSION_NEO4J_URI"] == "bolt://localhost:7687"
    assert "GEOFUSION_NEO4J_DATABASE" not in config.as_env_defaults()


def test_apply_local_dependency_defaults_does_not_override_existing_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dependency_file = tmp_path / "依赖.txt"
    dependency_file.write_text(
        "\n".join(
            [
                "Redis端口:6380",
                "Neo4j用户名:neo4j",
                "Neo4j密码:systemneo4j",
                "api-key:sk-test",
                'base_url="https://www.dmxapi.cn/v1"',
                'model="qwen3.5-397b-a17b"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GEOFUSION_CELERY_BROKER", "redis://localhost:6399/0")
    monkeypatch.setenv("GEOFUSION_LLM_MODEL", "custom-model")

    applied = apply_local_dependency_defaults(dependency_file)

    assert applied["GEOFUSION_CELERY_BROKER"] == "redis://localhost:6399/0"
    assert applied["GEOFUSION_LLM_MODEL"] == "custom-model"
    assert applied["GEOFUSION_CELERY_BACKEND"] == "redis://localhost:6380/0"
    assert applied["GEOFUSION_LLM_PROVIDER"] == "openai"


def test_read_local_dependency_config_rejects_invalid_redis_port(tmp_path: Path) -> None:
    dependency_file = tmp_path / "依赖.txt"
    dependency_file.write_text(
        "\n".join(
            [
                "Redis端口:not-a-number",
                "Neo4j用户名:neo4j",
                "Neo4j密码:systemneo4j",
                "api-key:sk-test",
                'base_url="https://www.dmxapi.cn/v1"',
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(DependencyConfigError, match="Redis"):
        read_local_dependency_config(dependency_file)


def test_find_missing_runtime_dependencies_reports_unavailable_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTHONPATH", raising=False)

    missing = find_missing_runtime_dependencies(
        module_names=[
            "json",
            "module_does_not_exist_for_geofusion",
        ]
    )

    assert missing == ["module_does_not_exist_for_geofusion"]


def test_apply_runtime_entrypoint_defaults_is_noop_during_pytest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dependency_file = tmp_path / "依赖.txt"
    dependency_file.write_text(
        "\n".join(
            [
                "Redis端口:6380",
                "Neo4j用户名:neo4j",
                "Neo4j密码:systemneo4j",
                "api-key:sk-test",
                'base_url="https://www.dmxapi.cn/v1"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_local_runtime.py::noop (call)")
    monkeypatch.delenv("GEOFUSION_LLM_PROVIDER", raising=False)

    applied = apply_runtime_entrypoint_defaults(dependency_file)

    assert applied == {}
    assert "GEOFUSION_LLM_PROVIDER" not in applied
