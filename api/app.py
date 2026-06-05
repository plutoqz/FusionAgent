from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from starlette.middleware.cors import CORSMiddleware

from api.routers.fusion import router as fusion_router
from api.routers.jobs import router as jobs_router
from api.routers.kg import router as kg_router
from api.routers.runs_v2 import router as runs_v2_router
from api.routers.scenario_runs import router as scenario_runs_router
from api.routers.settings import router as settings_router
from api.routers.validation_sessions import router as validation_sessions_router

DEFAULT_CORS_ORIGINS = (
    "http://127.0.0.1:5173",
    "http://localhost:5173",
)


def _default_frontend_dist_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "frontend" / "dist"


def _normalize_cors_origins(cors_origins: Sequence[str] | None) -> list[str]:
    if cors_origins is not None:
        return [origin.strip() for origin in cors_origins if origin.strip()]

    env_value = os.getenv("GEOFUSION_CORS_ORIGINS", "")
    if env_value.strip():
        return [origin.strip() for origin in env_value.split(",") if origin.strip()]

    return list(DEFAULT_CORS_ORIGINS)


def _resolve_frontend_path(frontend_dist_dir: Path, requested_path: str) -> Path | None:
    normalized_path = requested_path.strip("/")
    candidate = (frontend_dist_dir / normalized_path).resolve()

    try:
        candidate.relative_to(frontend_dist_dir.resolve())
    except ValueError:
        return None

    if candidate.is_file():
        return candidate
    return None


def _register_frontend_routes(app: FastAPI, frontend_dist_dir: Path) -> None:
    index_file = frontend_dist_dir / "index.html"
    if not index_file.is_file():
        return

    @app.get("/", include_in_schema=False)
    async def frontend_root() -> FileResponse:
        return FileResponse(index_file)

    @app.get("/{frontend_path:path}", include_in_schema=False)
    async def frontend_entry(frontend_path: str) -> FileResponse:
        if frontend_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")

        resolved_file = _resolve_frontend_path(frontend_dist_dir, frontend_path)
        if resolved_file is not None:
            return FileResponse(resolved_file)

        return FileResponse(index_file)


def create_app(frontend_dist_dir: Path | None = None, cors_origins: Sequence[str] | None = None) -> FastAPI:
    app = FastAPI(
        title="GeoFusion API",
        version="0.2.0",
        description="GeoFusion v1+v2 API for vector fusion and agent-driven workflow execution.",
    )
    normalized_cors_origins = _normalize_cors_origins(cors_origins)
    if normalized_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=normalized_cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    app.include_router(fusion_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(runs_v2_router, prefix="/api/v2")
    app.include_router(kg_router, prefix="/api/v2")
    app.include_router(scenario_runs_router, prefix="/api/v2")
    app.include_router(settings_router, prefix="/api/v2")
    app.include_router(validation_sessions_router, prefix="/api/v2")

    resolved_frontend_dist_dir = (frontend_dist_dir or _default_frontend_dist_dir()).resolve()
    if resolved_frontend_dist_dir.is_dir():
        _register_frontend_routes(app, resolved_frontend_dist_dir)

    return app
