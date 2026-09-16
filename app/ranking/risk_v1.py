"""Risk-based multi-signal prioritisation strategy (risk_v1)."""

from __future__ import annotations

import logging
import math
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


@register_strategy("risk_v1")
class RiskRanker:
    """Multi-signal risk ranker with non-parametric MAD and exposure scaling."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return "risk_v1"

    def compute_telemetry_risk(self, tf: TelemetryFeatures) -> float:
        """Compute telemetry risk score on 0-100 scale."""
        if tf.flagged_hours == 0:
            return 0.0

        p_score = min(1.0, tf.persistence_ratio) * 100.0
        s_score = min(1.0, tf.avg_anomaly_severity / self.config.max_severity_cap) * 100.0
        r_score = min(1.0, tf.recency_score) * 100.0

        raw_risk = (
            self.config.weight_persistence * p_score
            + self.config.weight_severity * s_score
            + self.config.weight_recency * r_score
        )
        adjusted_risk = raw_risk * tf.importance_multiplier
        return round(max(0.0, min(100.0, adjusted_risk)), 4)

    def compute_meter_impact(self, mf: MeterImpactFeatures) -> float:
        """Compute meter-read impact score on 0-100 scale."""
        if not mf.has_meter_data or mf.meters_expected == 0:
            return 0.0

        failure_ratio = 1.0 - mf.read_success_ratio
        degradation = mf.degradation_vs_history
        raw_impact = 0.60 * failure_ratio + 0.40 * degradation

        exposure_scale = min(1.0, math.log1p(mf.exposure_meters) / math.log1p(500.0))
        scaled_impact = raw_impact * exposure_scale * 100.0

        return round(max(0.0, min(100.0, scaled_impact)), 4)

    def compute_data_confidence(
        self, qa: QualityAssessment, mf: MeterImpactFeatures
    ) -> float:
        """Compute data confidence score on 0-100 scale."""
        penalty = qa.confidence_penalty
        if not mf.has_meter_data:
            penalty = min(1.0, penalty + 0.10)

        conf = (1.0 - penalty) * 100.0
        return round(max(0.0, min(100.0, conf)), 4)

    def score_single(
        self,
        tf: TelemetryFeatures,
        mf: MeterImpactFeatures,
        qa: QualityAssessment,
    ) -> float:
        """Calculate single gateway final composite score."""
        t_risk = self.compute_telemetry_risk(tf)
        m_impact = self.compute_meter_impact(mf)
        d_conf = self.compute_data_confidence(qa, mf)

        if mf.has_meter_data:
            final = (
                self.config.weight_telemetry_risk * t_risk
                + self.config.weight_meter_impact * m_impact
                + self.config.weight_data_confidence * d_conf
            )
        else:
            total_w = self.config.weight_telemetry_risk + self.config.weight_data_confidence
            final = (
                (self.config.weight_telemetry_risk / total_w) * t_risk
                + (self.config.weight_data_confidence / total_w) * d_conf
            )

        return round(max(0.0, min(100.0, final)), 4)

    def score_gateways(
        self,
        telemetry_feats: Dict[str, TelemetryFeatures],
        meter_feats: Dict[str, MeterImpactFeatures],
        assessments: Dict[str, QualityAssessment],
    ) -> List[ScoredGateway]:
        """Compute composite scores across all eligible gateways."""
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
                    importance_multiplier=1.0,
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

            t_risk = self.compute_telemetry_risk(tf)
            m_impact = self.compute_meter_impact(mf)
            d_conf = self.compute_data_confidence(qa, mf)

            if mf.has_meter_data:
                final = (
                    self.config.weight_telemetry_risk * t_risk
                    + self.config.weight_meter_impact * m_impact
                    + self.config.weight_data_confidence * d_conf
                )
            else:
                total_w = self.config.weight_telemetry_risk + self.config.weight_data_confidence
                final = (
                    (self.config.weight_telemetry_risk / total_w) * t_risk
                    + (self.config.weight_data_confidence / total_w) * d_conf
                )

            final = round(max(0.0, min(100.0, final)), 4)

            scored.append(
                ScoredGateway(
                    gateway_id=gw,
                    final_score=final,
                    telemetry_risk=t_risk,
                    meter_impact=m_impact,
                    data_confidence=d_conf,
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
        """Apply deterministic 4-key tie-breaking sort."""
        sorted_list = sorted(
            scored_gateways,
            key=lambda g: (
                -g.final_score,
                -g.meter_features.exposure_meters,
                -g.telemetry_features.total_recent_offline_sec,
                g.gateway_id,
            ),
        )
        return sorted_list[:visit_limit]
