from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError

from demoforge_api.db import check_database, database_engine
from demoforge_api.settings import Settings


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
