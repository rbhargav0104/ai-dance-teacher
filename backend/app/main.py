"""FastAPI application factory. Run: `uvicorn app.main:app` (one API worker in development)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import health, session
from app.config import get_settings
from app.errors import install_error_handlers
from app.logging_setup import configure_logging, install_request_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging()
    settings.data_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="AI Dance Teacher API",
        version=__version__,
        description="Private pose-based dance coaching API. Scores come only from measured movement.",  # noqa: E501
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    install_request_logging(app)
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(session.router)
    return app


app = create_app()
