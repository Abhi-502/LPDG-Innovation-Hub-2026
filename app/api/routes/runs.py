"""Run execution management and status endpoints."""

from __future__ import annotations

import datetime as dt
from fastapi import APIRouter, Depends, status

from app.config import AppConfig, get_config
from app.domain.models import CreateRunRequest, RunResponse
from app.services.ranking_service import RankingService
from app.services.run_service import RunService
from app.validation.input import validate_iso_date

router = APIRouter(prefix="/api/v1", tags=["Runs"])


def get_ranking_service(config: AppConfig = Depends(get_config)) -> RankingService:
    return RankingService(config)


def get_run_service(
    config: AppConfig = Depends(get_config),
    ranking_service: RankingService = Depends(get_ranking_service),
) -> RunService:
    return RunService(config, ranking_service)


@router.post(
    "/runs",
    response_model=RunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Trigger Prioritisation Execution Run",
)
def create_run(
    request: CreateRunRequest,
    run_service: RunService = Depends(get_run_service),
) -> RunResponse:
    """Synchronously execute prioritisation run across requested or all scored weeks.

    Enforces OS-level single execution lock; returns 409 Conflict if another run is active.
    """
    target_weeks = None
    if request.weeks:
        target_weeks = [validate_iso_date(w) for w in request.weeks]

    return run_service.execute_run(
        requested_weeks=target_weeks,
        ranking_method=request.ranking_method,
    )


@router.get(
    "/runs/{run_id}",
    response_model=RunResponse,
    summary="Get Execution Run Status",
)
def get_run_status(
    run_id: str,
    run_service: RunService = Depends(get_run_service),
) -> RunResponse:
    """Retrieve execution status, heartbeat, and artifacts for a specific run."""
    return run_service.get_run(run_id)
