from fastapi import FastAPI

from api.routers.fusion import router as fusion_router
from api.routers.jobs import router as jobs_router
from api.routers.runs_v2 import router as runs_v2_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="GeoFusion API",
        version="0.2.0",
        description="GeoFusion v1+v2 API for vector fusion and agent-driven workflow execution.",
    )
    app.include_router(fusion_router, prefix="/api/v1")
    app.include_router(jobs_router, prefix="/api/v1")
    app.include_router(runs_v2_router, prefix="/api/v2")
    return app
