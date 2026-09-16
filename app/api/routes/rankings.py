"""Weekly prediction rankings endpoint."""

from __future__ import annotations

import datetime as dt
from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.config import AppConfig, get_config
from app.domain.models import WeeklyPredictionsResponse
from app.services.ranking_service import RankingService
from app.services.run_service import RunService
from app.validation.input import validate_iso_date

router = APIRouter(prefix="/api/v1", tags=["Rankings"])


def get_ranking_service(config: AppConfig = Depends(get_config)) -> RankingService:
    return RankingService(config)


def get_run_service(
    config: AppConfig = Depends(get_config),
    ranking_service: RankingService = Depends(get_ranking_service),
) -> RunService:
    return RunService(config, ranking_service)


@router.get(
    "/weeks/{week_start}/predictions",
    response_model=WeeklyPredictionsResponse,
    summary="Get Weekly Gateway Predictions",
)
@router.get(
    "/weeks/{week_start}/rankings",
    response_model=WeeklyPredictionsResponse,
    summary="Get Weekly Gateway Rankings (Alias)",
    include_in_schema=False,
)
def get_weekly_predictions(
    week_start: str,
    run_id: Optional[str] = Query(None, description="Optional specific run identifier to resolve from"),
    ranking_method: Optional[str] = Query(None, description="Optional strategy override (e.g. 'risk_v1', 'baseline')"),
    run_service: RunService = Depends(get_run_service),
    config: AppConfig = Depends(get_config),
) -> WeeklyPredictionsResponse:
    """Retrieve top 15 ranked gateways for the requested Monday week cutoff."""
    target_date = validate_iso_date(week_start)
    method = ranking_method or config.ranking_method

    predictions = run_service.get_predictions_for_week(
        week_start=target_date,
        run_id=run_id,
        ranking_method=method,
    )

    return WeeklyPredictionsResponse(
        week_start=target_date.isoformat(),
        ranking_method=method,
        run_id=run_id,
        count=len(predictions),
        predictions=predictions,
    )


@router.get(
    "/predictions",
    response_model=WeeklyPredictionsResponse,
    summary="Get Latest Week Gateway Predictions",
)
def get_latest_predictions(
    week_start: Optional[str] = Query(None, description="Optional Monday date (YYYY-MM-DD). Defaults to latest week."),
    run_id: Optional[str] = Query(None, description="Optional specific run identifier to resolve from"),
    ranking_method: Optional[str] = Query(None, description="Optional strategy override"),
    run_service: RunService = Depends(get_run_service),
    config: AppConfig = Depends(get_config),
) -> WeeklyPredictionsResponse:
    """Ask for this week's 15 top-priority gateway visits."""
    target_date = validate_iso_date(week_start) if week_start else config.scored_weeks[-1]
    method = ranking_method or config.ranking_method

    predictions = run_service.get_predictions_for_week(
        week_start=target_date,
        run_id=run_id,
        ranking_method=method,
    )

    return WeeklyPredictionsResponse(
        week_start=target_date.isoformat(),
        ranking_method=method,
        run_id=run_id,
        count=len(predictions),
        predictions=predictions,
    )
