"""Gateway explainability and diagnostics endpoint."""

from __future__ import annotations

import datetime as dt
from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.config import AppConfig, get_config
from app.domain.models import GatewayEvaluationResponse
from app.services.gateway_service import GatewayService
from app.services.ranking_service import RankingService
from app.validation.input import validate_iso_date

router = APIRouter(prefix="/api/v1", tags=["Gateways"])


def get_gateway_service(config: AppConfig = Depends(get_config)) -> GatewayService:
    ranking_service = RankingService(config)
    return GatewayService(config, ranking_service)


@router.get(
    "/weeks/{week_start}/gateways/{gateway_id}",
    response_model=GatewayEvaluationResponse,
    summary="Get Gateway Explanation and Evaluation (by week)",
)
def evaluate_gateway_by_week(
    week_start: str,
    gateway_id: str,
    ranking_method: Optional[str] = Query(None, description="Optional strategy override ('risk_v1', 'baseline')"),
    gateway_service: GatewayService = Depends(get_gateway_service),
) -> GatewayEvaluationResponse:
    """Evaluate a specific gateway for a week cutoff, returning operational reasons and features."""
    target_date = validate_iso_date(week_start)
    return gateway_service.evaluate_gateway(
        monday=target_date,
        raw_gateway_id=gateway_id,
        ranking_method=ranking_method,
    )


@router.get(
    "/gateways/{gateway_id}",
    response_model=GatewayEvaluationResponse,
    summary="Get Gateway Explanation and Evaluation",
)
@router.get(
    "/gateways/{gateway_id}/explanation",
    response_model=GatewayEvaluationResponse,
    summary="Get Gateway Diagnostic Explanation (Alias)",
    include_in_schema=False,
)
def evaluate_gateway_direct(
    gateway_id: str,
    week_start: Optional[str] = Query(None, description="Target Monday date (YYYY-MM-DD). Defaults to latest scored week."),
    ranking_method: Optional[str] = Query(None, description="Optional strategy override ('risk_v1', 'baseline')"),
    config: AppConfig = Depends(get_config),
    gateway_service: GatewayService = Depends(get_gateway_service),
) -> GatewayEvaluationResponse:
    """Ask why a particular gateway is where it is, returning detailed scores, status, and explanations."""
    target_date = validate_iso_date(week_start) if week_start else config.scored_weeks[-1]
    return gateway_service.evaluate_gateway(
        monday=target_date,
        raw_gateway_id=gateway_id,
        ranking_method=ranking_method,
    )
