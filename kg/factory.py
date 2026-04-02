from __future__ import annotations

import logging
import os

from kg.inmemory_repository import InMemoryKGRepository
from kg.neo4j_repository import Neo4jKGRepository
from kg.repository import KGRepository
from utils.local_runtime import apply_runtime_entrypoint_defaults


def create_kg_repository() -> KGRepository:
    apply_runtime_entrypoint_defaults()
    backend = os.getenv("GEOFUSION_KG_BACKEND", "neo4j").lower().strip()
    logger = logging.getLogger("geofusion.kg")

    if backend == "neo4j":
        try:
            repo = Neo4jKGRepository.from_env()
            if repo is not None:
                logger.info("KG backend: neo4j")
                return repo
            logger.warning("KG backend neo4j selected but env not configured; fallback to in-memory seed")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to initialize neo4j backend: %s; fallback to in-memory seed", exc)
        return InMemoryKGRepository()

    if backend == "memory":
        logger.info("KG backend: in-memory")
        return InMemoryKGRepository()

    logger.warning("Unknown KG backend '%s'; fallback to in-memory seed", backend)
    return InMemoryKGRepository()
