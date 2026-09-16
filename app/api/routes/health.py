"""Health and readiness check endpoints."""

from __future__ import annotations

import datetime as dt
from fastapi import APIRouter, Depends

from app import __version__
from app.config import AppConfig, get_config
from app.domain.models import HealthResponse
from app.repositories.gateways import GatewayRepository
from app.repositories.telemetry import TelemetryRepository

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="System Health and Readiness")
def get_health(config: AppConfig = Depends(get_config)) -> HealthResponse:
    """Check API service health and verify data directory accessibility."""
    gw_repo = GatewayRepository(config)
    tel_repo = TelemetryRepository(config)
    ready = gw_repo.exists_on_disk() and tel_repo.exists_on_disk()

    return HealthResponse(
        status="healthy" if ready else "degraded",
        timestamp=dt.datetime.now(dt.timezone.utc).isoformat(),
        version=__version__,
        environment=config.app_env,
        data_dir_ready=ready,
        ranking_method=config.ranking_method,
    )
