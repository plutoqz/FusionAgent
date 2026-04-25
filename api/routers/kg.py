from __future__ import annotations

from fastapi import APIRouter

from kg.factory import create_kg_repository
from schemas.kg_graph import KgGraphResponse
from services.kg_graph_service import build_overview_graph


router = APIRouter(tags=["kg"])


@router.get("/kg/overview", response_model=KgGraphResponse)
async def get_kg_overview() -> KgGraphResponse:
    repo = create_kg_repository()
    try:
        return build_overview_graph(repo)
    finally:
        close = getattr(repo, "close", None)
        if callable(close):
            close()
