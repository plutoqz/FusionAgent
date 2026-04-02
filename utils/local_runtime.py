from __future__ import annotations

import importlib.util
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


DEFAULT_DEPENDENCY_FILE = Path(__file__).resolve().parents[1] / "依赖.txt"
DEFAULT_LLM_MODEL = "qwen3.5-397b-a17b"
DEFAULT_NEO4J_URI = "bolt://localhost:7687"
DEFAULT_RUNTIME_MODULES = (
    "fastapi",
    "uvicorn",
    "pydantic",
    "celery",
    "redis",
    "neo4j",
    "geopandas",
    "shapely",
    "fiona",
    "pyproj",
    "scipy",
    "pandas",
    "numpy",
    "rtree",
)


class DependencyConfigError(ValueError):
    """Raised when the local dependency file is present but malformed."""


@dataclass(frozen=True)
class LocalDependencyConfig:
    redis_port: int
    neo4j_user: str
    neo4j_password: str
    llm_api_key: str
    llm_base_url: str
    llm_model: str = DEFAULT_LLM_MODEL
    neo4j_uri: str = DEFAULT_NEO4J_URI
    neo4j_database: str | None = None

    def as_env_defaults(self) -> dict[str, str]:
        defaults = {
            "GEOFUSION_KG_BACKEND": "neo4j",
            "GEOFUSION_NEO4J_URI": self.neo4j_uri,
            "GEOFUSION_NEO4J_USER": self.neo4j_user,
            "GEOFUSION_NEO4J_PASSWORD": self.neo4j_password,
            "GEOFUSION_CELERY_BROKER": f"redis://localhost:{self.redis_port}/0",
            "GEOFUSION_CELERY_BACKEND": f"redis://localhost:{self.redis_port}/0",
            "GEOFUSION_LLM_PROVIDER": "openai",
            "GEOFUSION_LLM_BASE_URL": self.llm_base_url,
            "GEOFUSION_LLM_API_KEY": self.llm_api_key,
            "GEOFUSION_LLM_MODEL": self.llm_model,
        }
        if self.neo4j_database:
            defaults["GEOFUSION_NEO4J_DATABASE"] = self.neo4j_database
        return defaults


def _dependency_path(path: str | os.PathLike[str] | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    env_path = os.getenv("GEOFUSION_DEPENDENCY_FILE", "").strip()
    if env_path:
        return Path(env_path)
    return DEFAULT_DEPENDENCY_FILE


def _read_text_with_fallbacks(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise DependencyConfigError(f"Unable to decode dependency file: {path}")


def _search_required(pattern: str, text: str, field_name: str) -> str:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match or not match.group(1).strip():
        raise DependencyConfigError(f"Missing required dependency field: {field_name}")
    return match.group(1).strip()


def _search_optional(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.IGNORECASE)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def read_local_dependency_config(
    path: str | os.PathLike[str] | Path | None = None,
    *,
    required: bool = False,
) -> LocalDependencyConfig | None:
    dependency_path = _dependency_path(path)
    if not dependency_path.exists():
        if required:
            raise DependencyConfigError(f"Dependency file not found: {dependency_path}")
        return None

    text = _read_text_with_fallbacks(dependency_path)
    redis_port_raw = _search_required(r"Redis端口\s*[:：]\s*([^\s]+)", text, "Redis端口")
    neo4j_user = _search_required(r"Neo4j用户名\s*[:：]\s*([^\s]+)", text, "Neo4j用户名")
    neo4j_password = _search_required(r"Neo4j密码\s*[:：]\s*([^\s]+)", text, "Neo4j密码")
    llm_api_key = _search_required(r"api-key\s*[:：]\s*([^\s]+)", text, "api-key")
    llm_base_url = _search_required(r'base_url\s*=\s*"([^"]+)"', text, "base_url")

    try:
        redis_port = int(redis_port_raw)
    except ValueError as exc:
        raise DependencyConfigError(f"Redis端口 must be an integer, got: {redis_port_raw}") from exc

    llm_model = (
        _search_optional(r'model\s*=\s*"([^"]+)"', text)
        or _search_optional(r"模型\s*[:：]\s*([^\s]+)", text)
        or DEFAULT_LLM_MODEL
    )
    neo4j_database = (
        _search_optional(r"Neo4j数据库(?:名)?\s*[:：]\s*([^\s]+)", text)
        or _search_optional(r"GEOFUSION_NEO4J_DATABASE\s*[:：=]\s*([^\s]+)", text)
    )
    neo4j_uri = (
        _search_optional(r"Neo4j地址\s*[:：]\s*([^\s]+)", text)
        or _search_optional(r"GEOFUSION_NEO4J_URI\s*[:：=]\s*([^\s]+)", text)
        or DEFAULT_NEO4J_URI
    )

    return LocalDependencyConfig(
        redis_port=redis_port,
        neo4j_user=neo4j_user,
        neo4j_password=neo4j_password,
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url.rstrip("/"),
        llm_model=llm_model,
        neo4j_uri=neo4j_uri,
        neo4j_database=neo4j_database,
    )


def apply_local_dependency_defaults(
    path: str | os.PathLike[str] | Path | None = None,
    *,
    required: bool = False,
) -> dict[str, str]:
    config = read_local_dependency_config(path, required=required)
    defaults = config.as_env_defaults() if config is not None else {}
    applied: dict[str, str] = {}
    for key, default_value in defaults.items():
        value = os.getenv(key)
        if value is None or value == "":
            os.environ[key] = default_value
            value = default_value
        applied[key] = value
    return applied


def apply_runtime_entrypoint_defaults(
    path: str | os.PathLike[str] | Path | None = None,
    *,
    required: bool = False,
) -> dict[str, str]:
    if os.getenv("PYTEST_CURRENT_TEST") or "pytest" in sys.modules:
        return {}
    return apply_local_dependency_defaults(path, required=required)


def find_missing_runtime_dependencies(module_names: Iterable[str] | None = None) -> list[str]:
    names = tuple(module_names or DEFAULT_RUNTIME_MODULES)
    missing: list[str] = []
    for name in names:
        if importlib.util.find_spec(name) is None:
            missing.append(name)
    return missing
