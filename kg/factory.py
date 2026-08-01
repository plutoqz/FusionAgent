from __future__ import annotations

import logging
import os
import sys

from kg.inmemory_repository import InMemoryKGRepository
from kg.knowledge_release import get_knowledge_identity
from kg.neo4j_repository import Neo4jKGRepository
from kg.policy_registry import default_policy_registry
from kg.repository import KGRepository
from utils.local_runtime import apply_runtime_entrypoint_defaults


def create_kg_repository() -> KGRepository:
    apply_runtime_entrypoint_defaults()
    running_tests = bool(os.getenv("PYTEST_CURRENT_TEST") or "pytest" in sys.modules)
    backend = os.getenv("GEOFUSION_KG_BACKEND", "memory" if running_tests else "neo4j").lower().strip()
    default_mode = "development" if running_tests else "strict"
    runtime_mode = os.getenv("GEOFUSION_KG_RUNTIME_MODE", default_mode).lower().strip()
    if runtime_mode not in {"strict", "research", "development"}:
        raise RuntimeError(
            "GEOFUSION_KG_RUNTIME_MODE must be strict, research, or development, "
            f"got {runtime_mode!r}"
        )

    policy_registry = default_policy_registry()
    runtime_gates = policy_registry.runtime_gates()
    backend_fallback_policy = policy_registry.backend_fallback_policy()
    configured_experience_policy = os.getenv("GEOFUSION_KG_EXPERIENCE_POLICY")
    if configured_experience_policy:
        experience_policy = configured_experience_policy.lower().strip()
    elif runtime_mode in {"strict", "research"}:
        experience_policy = str(runtime_gates["experience_policy"]).lower().strip()
    else:
        experience_policy = "adaptive"
    if runtime_mode in {"strict", "research"} and experience_policy != "pinned_snapshot":
        raise RuntimeError(
            f"KG {runtime_mode} mode requires experience_policy='pinned_snapshot', "
            f"got {experience_policy!r}"
        )

    expected_identity = get_knowledge_identity()
    logger = logging.getLogger("geofusion.kg")

    if backend == "neo4j":
        try:
            repo = Neo4jKGRepository.from_env(
                experience_policy=experience_policy,
                expected_knowledge_identity=expected_identity,
            )
            logger.info(
                "KG backend: neo4j (namespace=%s, release=%s, mode=%s)",
                repo.graph_namespace,
                expected_identity["release_id"],
                runtime_mode,
            )
            return repo
        except Exception as exc:  # noqa: BLE001
            fallback_allowed = runtime_mode == "development" and backend_fallback_policy in {
                "forbidden_in_strict_mode",
                "memory_in_development",
            }
            if fallback_allowed:
                logger.warning(
                    "Neo4j KG initialization failed; using policy-authorized in-memory "
                    "development fallback (policy=%s)",
                    backend_fallback_policy,
                )
                return InMemoryKGRepository(
                    experience_policy=experience_policy,
                    knowledge_identity=expected_identity,
                )
            raise RuntimeError(
                "Neo4j KG initialization failed in "
                f"{runtime_mode} mode; fallback is forbidden by policy "
                f"{backend_fallback_policy!r}"
            ) from exc

    if backend == "memory":
        logger.info(
            "KG backend: in-memory (release=%s, mode=%s)",
            expected_identity["release_id"],
            runtime_mode,
        )
        return InMemoryKGRepository(
            experience_policy=experience_policy,
            knowledge_identity=expected_identity,
        )

    raise RuntimeError(f"Unsupported GEOFUSION_KG_BACKEND value: {backend!r}")
