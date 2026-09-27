from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from tech_market_backend.platform.database import create_database_engine, session_factory

from tech_market_api.config import load_settings
from tech_market_api.market import MarketNotFoundError, get_market_reader, routes
from tech_market_api.postgres_reader import PostgresMarketReader


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(title="Tech Market Intelligence API", version="1.0.0")
    if settings.DATABASE_URL is not None:
        engine = create_database_engine(settings.DATABASE_URL.get_secret_value())
        reader = PostgresMarketReader(session_factory(engine))
        app.dependency_overrides[get_market_reader] = lambda: reader

    @app.exception_handler(MarketNotFoundError)
    async def market_not_found(_: Request, error: MarketNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "details": None,
                    "request_id": str(uuid4()),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {
                        "errors": [
                            {
                                "type": item["type"],
                                "loc": list(item["loc"]),
                                "msg": item["msg"],
                            }
                            for item in error.errors()
                        ]
                    },
                    "request_id": str(uuid4()),
                }
            },
        )

    for router in routes():
        app.include_router(router)

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app


app = create_app()
