"""Standard 3-sigma anomaly counting baseline strategy (baseline)."""

from __future__ import annotations

import logging
from typing import Dict, List
from app.config import AppConfig
from app.domain.models import (
    MeterImpactFeatures,
    QualityAssessment,
    ScoredGateway,
    TelemetryFeatures,
)
from app.ranking.base import register_strategy

logger = logging.getLogger(__name__)


@register_strategy("baseline")
class Baseline3SigmaRanker:
    """Baseline ranker relying strictly on anomaly breach count and read failure."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return "baseline"

    def score_single(
        self,
        tf: TelemetryFeatures,
        mf: MeterImpactFeatures,
        qa: QualityAssessment,
    ) -> float:
        """Calculate score using basic 3-sigma persistence and meter failure rate."""
        telemetry_score = tf.persistence_ratio * 70.0 + min(30.0, (tf.avg_anomaly_severity / 5.0) * 30.0)
        meter_score = (1.0 - mf.read_success_ratio) * 100.0 if mf.has_meter_data else 0.0
        final = 0.80 * telemetry_score + 0.20 * meter_score
        return round(max(0.0, min(100.0, final)), 4)

    def score_gateways(
        self,
        telemetry_feats: Dict[str, TelemetryFeatures],
        meter_feats: Dict[str, MeterImpactFeatures],
        assessments: Dict[str, QualityAssessment],
    ) -> List[ScoredGateway]:
        """Score gateways using baseline logic."""
        scored: List[ScoredGateway] = []

        for gw, qa in assessments.items():
            if not qa.is_eligible:
                continue

            tf = telemetry_feats.get(
                gw,
                TelemetryFeatures(
                    gateway_id=gw,
                    flagged_hours=0,
                    total_detection_hours=0,
                    persistence_ratio=0.0,
                    avg_anomaly_severity=0.0,
                    max_anomaly_severity=0.0,
                    recency_score=0.0,
                    worst_metric="none",
                    total_recent_offline_sec=0.0,
                ),
            )
            mf = meter_feats.get(
                gw,
                MeterImpactFeatures(
                    gateway_id=gw,
                    meters_expected=0,
                    meters_read=0,
                    read_success_ratio=1.0,
                    degradation_vs_history=0.0,
                    exposure_meters=0,
                    has_meter_data=False,
                ),
            )

            final = self.score_single(tf, mf, qa)
            scored.append(
                ScoredGateway(
                    gateway_id=gw,
                    final_score=final,
                    telemetry_risk=round(tf.persistence_ratio * 100.0, 4),
                    meter_impact=round((1.0 - mf.read_success_ratio) * 100.0 if mf.has_meter_data else 0.0, 4),
                    data_confidence=100.0,
                    telemetry_features=tf,
                    meter_features=mf,
                    quality_assessment=qa,
                )
            )

        return scored

    def rank_gateways(
        self,
        scored_gateways: List[ScoredGateway],
        visit_limit: int = 15,
    ) -> List[ScoredGateway]:
        """Sort by score, recent offline duration, then gateway_id."""
        sorted_list = sorted(
            scored_gateways,
            key=lambda g: (
                -g.final_score,
                -g.telemetry_features.total_recent_offline_sec,
                g.gateway_id,
            ),
        )
        return sorted_list[:visit_limit]
