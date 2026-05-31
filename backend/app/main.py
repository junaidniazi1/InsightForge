from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import ai, dashboards, datasets, health, workbench, db_connections


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="InsightForge API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(datasets.router)
    app.include_router(dashboards.router)
    app.include_router(ai.router)
    app.include_router(workbench.router)
    app.include_router(db_connections.router)
    return app


app = create_app()
