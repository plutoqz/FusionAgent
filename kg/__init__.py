from __future__ import annotations

from typing import Any

__all__ = ["KGRepository", "create_kg_repository"]


def __getattr__(name: str) -> Any:
    if name == "KGRepository":
        from kg.repository import KGRepository

        return KGRepository
    if name == "create_kg_repository":
        from kg.factory import create_kg_repository

        return create_kg_repository
    raise AttributeError(name)

