"""FastAPI application factory and exception handlers."""

from __future__ import annotations

import logging
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import gateways, health, rankings, runs
from app.config import AppConfig, get_config
from app.domain.errors import DomainError

logger = logging.getLogger(__name__)


def create_app(config: Optional[AppConfig] = None) -> FastAPI:
    """Create and configure FastAPI application instance."""
    app_config = config or get_config()

    app = FastAPI(
        title="Gateway Visit Prioritisation Engine API",
        version=__version__,
        description="LPDG Innovation Hub Selection Challenge 2026 — Part 2 Software Development API",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Allow CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Domain error handler
    @app.exception_handler(DomainError)
    async def domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
        logger.warning("Domain error [%d]: %s", exc.status_code, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.message, "status_code": exc.status_code},
        )

    # Generic unhandled exception handler
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error occurred.", "status_code": 500},
        )

    # Include API routers
    app.include_router(health.router)
    app.include_router(rankings.router)
    app.include_router(gateways.router)
    app.include_router(runs.router)

    @app.get("/", include_in_schema=False)
    def root():
        return {
            "title": "Gateway Visit Prioritisation Engine API",
            "version": __version__,
            "docs": "/docs",
            "health": "/health",
            "predictions": "/api/v1/predictions",
        }

    return app


app = create_app()
