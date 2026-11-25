from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.base import RequestResponseEndpoint

from demoforge_api.analysis.routes import analysis_router
from demoforge_api.auth import TokenVerifier
from demoforge_api.catalog.routes import catalog_router
from demoforge_api.db import check_database, database_engine
from demoforge_api.discovery.routes import discovery_router
from demoforge_api.discovery.storage import DiscoveryStorage
from demoforge_api.opportunities import opportunity_router
from demoforge_api.planning.routes import planning_router
from demoforge_api.settings import Settings
from demoforge_api.storyboard.routes import storyboard_router
from demoforge_api.workspaces import workspace_router


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["ok", "unavailable"]


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings if settings is not None else Settings()
    engine = database_engine(configuration.database_url) if configuration.database_url else None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if engine is not None:
                engine.dispose()

    app = FastAPI(title="DemoForge AI", version="0.0.0", lifespan=lifespan)

    @app.middleware("http")
    async def private_workspace_responses(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/v1/workspaces"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(SQLAlchemyError)
    async def safe_database_error(_: Request, error: SQLAlchemyError) -> JSONResponse:
        state = getattr(getattr(error, "orig", None), "sqlstate", None)
        if state == "42501":
            return JSONResponse({"detail": "Workspace action denied"}, status_code=403)
        if state == "23503":
            return JSONResponse(
                {"detail": "Referenced account or workspace not found"}, status_code=404
            )
        return JSONResponse({"detail": "Workspace service unavailable"}, status_code=503)

    verifier = TokenVerifier(configuration)
    app.include_router(workspace_router(engine, verifier))
    app.include_router(opportunity_router(engine, verifier))
    app.include_router(discovery_router(engine, verifier, DiscoveryStorage(configuration)))
    app.include_router(analysis_router(engine, verifier, configuration))
    app.include_router(planning_router(engine, verifier))
    app.include_router(catalog_router(engine, verifier))
    app.include_router(storyboard_router(engine, verifier))

    @app.get("/health/live", response_model=HealthResponse)
    def liveness(response: Response) -> HealthResponse:
        response.headers["Cache-Control"] = "no-store"
        return HealthResponse(status="ok")

    @app.get(
        "/health/ready", response_model=HealthResponse, responses={503: {"model": HealthResponse}}
    )
    def readiness(response: Response) -> HealthResponse:
        response.headers["Cache-Control"] = "no-store"
        if engine is not None:
            try:
                check_database(engine)
            except SQLAlchemyError:
                # Avoid including driver errors or database identifiers in responses.
                pass
            else:
                return HealthResponse(status="ok")
        response.status_code = 503
        return HealthResponse(status="unavailable")

    return app
