"""Gateway evaluation service for diagnostics and operations."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

from app.config import AppConfig
from app.domain.errors import GatewayNotFoundError
from app.domain.models import (
    GatewayEvaluationResponse,
    GatewayStatus,
)
from app.explanations.builder import ExplanationBuilder
from app.repositories.gateways import GatewayRepository
from app.services.ranking_service import RankingService
from app.validation.input import validate_hex_gateway_id

logger = logging.getLogger(__name__)


class GatewayService:
    """Provides single-gateway operational evaluations and explainability."""

    def __init__(
        self,
        config: AppConfig,
        ranking_service: RankingService,
        gateway_repo: Optional[GatewayRepository] = None,
        explanation_builder: Optional[ExplanationBuilder] = None,
    ) -> None:
        self.config = config
        self.ranking_service = ranking_service
        self.gateway_repo = gateway_repo or GatewayRepository(config)
        self.explanation_builder = explanation_builder or ExplanationBuilder(config)

    def evaluate_gateway(
        self,
        monday: dt.date,
        raw_gateway_id: str,
        ranking_method: Optional[str] = None,
    ) -> GatewayEvaluationResponse:
        """Evaluate a gateway for a given week cutoff."""
        # 1. Normalise & validate format
        norm_id = validate_hex_gateway_id(raw_gateway_id)

        # 2. Check existence in master
        master = self.gateway_repo.get_gateway(norm_id)
        if master is None:
            raise GatewayNotFoundError(norm_id)

        # 3. Validate scoring week
        self.ranking_service.validate_week(monday)
        strategy = self.ranking_service.get_strategy(ranking_method)

        # 4. Evaluate full week state
        scored_list, assessments, telemetry_feats, meter_feats = (
            self.ranking_service.evaluate_week_full(monday, ranking_method=strategy.name)
        )

        qa = assessments.get(norm_id)

        # Check if ineligible
        if qa is None or not qa.is_eligible:
            reason = self.explanation_builder.build_ineligible_reason(master, monday, qa)
            return GatewayEvaluationResponse(
                gateway_id=norm_id,
                week_start=monday.isoformat(),
                status=GatewayStatus.INELIGIBLE,
                rank=None,
                score=None,
                ranking_method=strategy.name,
                reason=reason,
                is_eligible=False,
                details={
                    "tenant": master.tenant,
                    "region": master.region,
                    "site_type": master.site_type,
                    "hw_model": master.hw_model,
                    "installed_on": master.installed_on.isoformat() if master.installed_on else None,
                    "decommissioned_on": master.decommissioned_on.isoformat() if master.decommissioned_on else None,
                    "n_meters_installed": master.n_meters_installed,
                    "reference_days": qa.reference_days_count if qa else 0,
                    "detection_days": qa.detection_days_count if qa else 0,
                    "rejection_reason": qa.rejection_reason if qa else "Not active",
                },
            )

        # Gateway is eligible - determine rank in sorted order
        # Rank all eligible gateways using the strategy's sorting logic
        all_sorted = sorted(
            scored_list,
            key=lambda g: (
                -g.final_score,
                -g.meter_features.exposure_meters,
                -g.telemetry_features.total_recent_offline_sec,
                g.gateway_id,
            ),
        )

        target_gw = next((g for g in scored_list if g.gateway_id == norm_id), None)
        assert target_gw is not None

        overall_rank = next(
            (idx for idx, g in enumerate(all_sorted, start=1) if g.gateway_id == norm_id),
            len(all_sorted),
        )

        tf = target_gw.telemetry_features
        mf = target_gw.meter_features

        details = {
            "tenant": master.tenant,
            "region": master.region,
            "site_type": master.site_type,
            "hw_model": master.hw_model,
            "installed_on": master.installed_on.isoformat(),
            "decommissioned_on": master.decommissioned_on.isoformat() if master.decommissioned_on else None,
            "n_meters_installed": master.n_meters_installed,
            "score_breakdown": {
                "final_score": target_gw.final_score,
                "telemetry_risk": target_gw.telemetry_risk,
                "meter_impact": target_gw.meter_impact,
                "data_confidence": target_gw.data_confidence,
            },
            "telemetry_features": {
                "flagged_hours": tf.flagged_hours,
                "total_detection_hours": tf.total_detection_hours,
                "persistence_ratio": round(tf.persistence_ratio, 4),
                "avg_anomaly_severity": round(tf.avg_anomaly_severity, 4),
                "worst_metric": tf.worst_metric,
                "total_recent_offline_sec": tf.total_recent_offline_sec,
            },
            "meter_features": {
                "meters_expected": mf.meters_expected,
                "meters_read": mf.meters_read,
                "read_success_ratio": round(mf.read_success_ratio, 4),
                "exposure_meters": mf.exposure_meters,
                "has_meter_data": mf.has_meter_data,
            },
            "quality": {
                "is_full_quality": qa.is_full_quality,
                "reference_days": qa.reference_days_count,
                "detection_days": qa.detection_days_count,
            },
        }

        if overall_rank <= self.config.visit_limit:
            reason = self.explanation_builder.build_ranked_reason(target_gw, overall_rank)
            return GatewayEvaluationResponse(
                gateway_id=norm_id,
                week_start=monday.isoformat(),
                status=GatewayStatus.RANKED_TOP_15,
                rank=overall_rank,
                score=target_gw.final_score,
                ranking_method=strategy.name,
                reason=reason,
                is_eligible=True,
                details=details,
            )
        else:
            reason = self.explanation_builder.build_unranked_reason(target_gw, overall_rank)
            return GatewayEvaluationResponse(
                gateway_id=norm_id,
                week_start=monday.isoformat(),
                status=GatewayStatus.ELIGIBLE_UNRANKED,
                rank=overall_rank,
                score=target_gw.final_score,
                ranking_method=strategy.name,
                reason=reason,
                is_eligible=True,
                details=details,
            )
