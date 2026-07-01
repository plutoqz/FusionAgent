from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from utils.local_runtime import (
    DEFAULT_GRAPH_NAMESPACE,
    DependencyConfigError,
    apply_local_dependency_defaults,
    apply_runtime_entrypoint_defaults,
    build_local_runtime_env_defaults,
    find_missing_runtime_dependencies,
    read_dotenv_defaults,
    read_local_dependency_config,
)
from scripts.start_local import _build_env, _prepare_neo4j


MANAGED_ENV_KEYS = [
    "GEOFUSION_KG_BACKEND",
    "GEOFUSION_NEO4J_URI",
    "GEOFUSION_NEO4J_USER",
    "GEOFUSION_NEO4J_PASSWORD",
    "GEOFUSION_NEO4J_DATABASE",
    "GEOFUSION_GRAPH_NAMESPACE",
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
                "Neo4j数据库:neo4j",
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
    assert config.neo4j_database == "neo4j"
    assert config.llm_api_key == "sk-test"
    assert config.llm_base_url == "https://www.dmxapi.cn/v1"
    assert config.llm_model == "qwen3.5-397b-a17b"
    assert config.as_env_defaults()["GEOFUSION_CELERY_BROKER"] == "redis://localhost:6380/0"
    assert config.as_env_defaults()["GEOFUSION_NEO4J_URI"] == "bolt://localhost:7687"
    assert config.as_env_defaults()["GEOFUSION_NEO4J_DATABASE"] == "neo4j"
    assert config.as_env_defaults()["GEOFUSION_GRAPH_NAMESPACE"] == DEFAULT_GRAPH_NAMESPACE


def test_read_local_dependency_config_reads_optional_graph_namespace(tmp_path: Path) -> None:
    dependency_file = tmp_path / "依赖.txt"
    dependency_file.write_text(
        "\n".join(
            [
                "Redis端口:6380",
                "Neo4j用户名:neo4j",
                "Neo4j密码:systemneo4j",
                "图命名空间:fusionagent-lab",
                "api-key:sk-test",
                'base_url="https://www.dmxapi.cn/v1"',
            ]
        ),
        encoding="utf-8",
    )

    config = read_local_dependency_config(dependency_file)

    assert config.graph_namespace == "fusionagent-lab"
    assert config.as_env_defaults()["GEOFUSION_GRAPH_NAMESPACE"] == "fusionagent-lab"


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


def test_prepare_neo4j_memory_summary_marks_contract_as_passed() -> None:
    summary = _prepare_neo4j({"GEOFUSION_KG_BACKEND": "memory"})

    assert summary["isolation_mode"] == "memory"
    assert summary["kg_contract_ok"] is True
    assert summary["missing_seed_labels"] == {}


def test_build_env_supports_isolated_runtime_roots_and_redis_db(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scripts.start_local.build_local_runtime_env_defaults",
        lambda mode="full", require_dependency_file=True: {
            "GEOFUSION_CELERY_BROKER": "redis://localhost:6380/0",
            "GEOFUSION_CELERY_BACKEND": "redis://localhost:6380/0",
            "GEOFUSION_LLM_MODEL": "qwen-test",
        },
    )

    env = _build_env(
        8012,
        runs_root=tmp_path / "isolated-runs",
        redis_db=7,
        disable_recovery=True,
        disable_scheduler=True,
    )

    assert env["GEOFUSION_RUNS_ROOT"] == str(tmp_path / "isolated-runs")
    assert env["GEOFUSION_CELERY_BROKER"] == "redis://localhost:6380/7"
    assert env["GEOFUSION_CELERY_BACKEND"] == "redis://localhost:6380/7"
    assert env["GEOFUSION_RECOVERY_ENABLED"] == "0"
    assert env["GEOFUSION_SCHEDULER_ENABLED"] == "0"


def test_fast_mode_env_defaults_do_not_require_dependency_file(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GEOFUSION_DEPENDENCY_FILE", str(Path("missing-dependency-file.txt").resolve()))

    env = _build_env(8021, mode="fast")

    assert env["GEOFUSION_KG_BACKEND"] == "memory"
    assert env["GEOFUSION_LLM_PROVIDER"] == "mock"
    assert env["GEOFUSION_CELERY_EAGER"] == "1"
    assert env["PYTHONUTF8"] == "1"
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_runtime_defaults_precedence_env_dependency_dotenv_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dependency_file = tmp_path / "依赖.txt"
    dependency_file.write_text(
        "\n".join(
            [
                "Redis端口:6388",
                "Neo4j用户名:neo4j",
                "Neo4j密码:from-dependency",
                "api-key:sk-dependency",
                'base_url="https://dependency.example/v1"',
            ]
        ),
        encoding="utf-8",
    )
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(
        "\n".join(
            [
                "GEOFUSION_LLM_PROVIDER=mock",
                "GEOFUSION_NEO4J_PASSWORD=from-dotenv",
                "GEOFUSION_CELERY_EAGER=1",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GEOFUSION_LLM_PROVIDER", "env-provider")

    defaults = build_local_runtime_env_defaults(
        mode="full",
        dependency_path=dependency_file,
        dotenv_path=dotenv_file,
        require_dependency_file=True,
    )
    env = os.environ.copy()
    for key, value in defaults.items():
        env.setdefault(key, value)

    assert defaults["GEOFUSION_NEO4J_PASSWORD"] == "from-dependency"
    assert defaults["GEOFUSION_CELERY_EAGER"] == "1"
    assert env["GEOFUSION_LLM_PROVIDER"] == "env-provider"
    assert read_dotenv_defaults(dotenv_file)["GEOFUSION_NEO4J_PASSWORD"] == "from-dotenv"


def test_celery_beat_schedule_can_be_disabled_for_isolated_runtime(tmp_path: Path) -> None:
    code = (
        "from worker.celery_app import describe_beat_schedule; "
        "print(describe_beat_schedule())"
    )
    env = os.environ.copy()
    env["GEOFUSION_SCHEDULER_ENABLED"] = "0"
    env["GEOFUSION_RUNS_ROOT"] = str(tmp_path / "runs")

    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.stdout.strip() == "{}"
