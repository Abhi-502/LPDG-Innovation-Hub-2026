"""Ranking service orchestrating repositories, features, strategies, and outputs."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Dict, List, Optional, Set, Tuple
import pandas as pd

from app.config import AppConfig
from app.domain.errors import InvalidRequestError, WeekNotSupportedError
from app.domain.models import (
    MeterImpactFeatures,
    PredictionItem,
    QualityAssessment,
    ScoredGateway,
    TelemetryFeatures,
)
from app.domain.protocols import RankingStrategy
from app.explanations.builder import ExplanationBuilder
from app.features.builder import FeatureBuilder
from app.ranking.base import get_ranking_strategy
from app.repositories.gateways import GatewayRepository
from app.repositories.meter_reads import MeterReadRepository
from app.repositories.telemetry import TelemetryRepository
from app.validation.input import DataQualityGate

logger = logging.getLogger(__name__)


class RankingService:
    """Orchestrates weekly scoring, ranking strategies, and prediction generation."""

    def __init__(
        self,
        config: AppConfig,
        gateway_repo: Optional[GatewayRepository] = None,
        telemetry_repo: Optional[TelemetryRepository] = None,
        meter_repo: Optional[MeterReadRepository] = None,
        feature_builder: Optional[FeatureBuilder] = None,
        dq_gate: Optional[DataQualityGate] = None,
        explanation_builder: Optional[ExplanationBuilder] = None,
    ) -> None:
        self.config = config
        self.gateway_repo = gateway_repo or GatewayRepository(config)
        self.telemetry_repo = telemetry_repo or TelemetryRepository(config)
        self.meter_repo = meter_repo or MeterReadRepository(config)
        self.feature_builder = feature_builder or FeatureBuilder(config)
        self.dq_gate = dq_gate or DataQualityGate(config)
        self.explanation_builder = explanation_builder or ExplanationBuilder(config)

    def get_strategy(self, ranking_method: Optional[str] = None) -> RankingStrategy:
        """Resolve ranking strategy implementation."""
        method = ranking_method or self.config.ranking_method
        return get_ranking_strategy(method, self.config)

    def validate_week(self, monday: dt.date) -> None:
        """Verify that requested date is within supported scoring window."""
        if monday not in self.config.scored_weeks:
            raise WeekNotSupportedError(str(monday))

    def evaluate_week_full(
        self,
        monday: dt.date,
        ranking_method: Optional[str] = None,
    ) -> Tuple[
        List[ScoredGateway],
        Dict[str, QualityAssessment],
        Dict[str, TelemetryFeatures],
        Dict[str, MeterImpactFeatures],
    ]:
        """Compute complete gateway scoring state for a single target Monday."""
        self.validate_week(monday)
        strategy = self.get_strategy(ranking_method)
        cutoff_utc = pd.Timestamp(monday, tz=self.config.timezone)

        master_df = self.gateway_repo.load_master()
        active_gateways = self.dq_gate.filter_active_gateways(master_df, monday)

        telemetry_df = self.telemetry_repo.load_telemetry(
            cutoff_utc=cutoff_utc,
            trailing_days=self.config.total_trailing_days,
            required_metrics=list(self.config.telemetry_metrics),
            importance_metrics=list(self.config.importance_metrics),
        )

        assessments = self.dq_gate.assess_telemetry_history(
            telemetry_df=telemetry_df,
            active_gateway_ids=active_gateways,
            cutoff_utc=cutoff_utc,
        )
        eligible_gateways = {gw for gw, a in assessments.items() if a.is_eligible}

        telemetry_feats = self.feature_builder.extract_telemetry_features(
            telemetry_df=telemetry_df,
            cutoff_utc=cutoff_utc,
            eligible_gateways=eligible_gateways,
        )

        meter_df = self.meter_repo.load_meter_reads(
            cutoff_date=monday,
            lookback_weeks=4,
        )
        meter_feats = self.feature_builder.extract_meter_impact_features(
            meter_df=meter_df,
            master_df=master_df,
            cutoff_date=monday,
            eligible_gateways=eligible_gateways,
        )

        scored = strategy.score_gateways(
            telemetry_feats=telemetry_feats,
            meter_feats=meter_feats,
            assessments=assessments,
        )

        return scored, assessments, telemetry_feats, meter_feats

    def get_top_ranked_gateways(
        self,
        monday: dt.date,
        ranking_method: Optional[str] = None,
    ) -> List[ScoredGateway]:
        """Compute and return top 15 ranked gateways."""
        scored, _, _, _ = self.evaluate_week_full(monday, ranking_method)
        strategy = self.get_strategy(ranking_method)
        return strategy.rank_gateways(scored, visit_limit=self.config.visit_limit)

    def get_predictions_for_week(
        self,
        monday: dt.date,
        ranking_method: Optional[str] = None,
    ) -> List[PredictionItem]:
        """Return formatted prediction items for top 15 ranked gateways."""
        top_gateways = self.get_top_ranked_gateways(monday, ranking_method)
        strategy = self.get_strategy(ranking_method)

        items: List[PredictionItem] = []
        for rank_idx, gw in enumerate(top_gateways, start=1):
            reason_text = self.explanation_builder.build_ranked_reason(gw, rank_idx)
            items.append(
                PredictionItem(
                    rank=rank_idx,
                    gateway_id=gw.gateway_id,
                    score=round(float(gw.final_score), 4),
                    reason=reason_text,
                    ranking_method=strategy.name,
                )
            )
        return items
