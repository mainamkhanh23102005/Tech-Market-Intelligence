from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from tech_market_api.config import load_settings


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


def create_app() -> FastAPI:
    load_settings()
    app = FastAPI(title="Tech Market Intelligence API", version="0.0.0")

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    return app


app = create_app()
