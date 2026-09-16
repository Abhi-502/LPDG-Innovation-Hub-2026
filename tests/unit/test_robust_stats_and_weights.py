"""Unit tests for robust statistics, scale floors, and score weight rebalancing."""

from __future__ import annotations

import pandas as pd
import pytest

from app.config import AppConfig
from app.domain.models import MeterImpactFeatures, QualityAssessment, TelemetryFeatures
from app.ranking.risk_v1 import RiskRanker


def test_missing_meter_data_rebalances_weights(test_config: AppConfig):
    """Verify that when meter data is absent, weights dynamically rebalance between telemetry and confidence."""
    ranker = RiskRanker(test_config)
    gw = "020000000001"

    tf = TelemetryFeatures(
        gateway_id=gw,
        flagged_hours=20,
        total_detection_hours=168,
        persistence_ratio=20 / 168,
        avg_anomaly_severity=4.0,
        max_anomaly_severity=5.0,
        recency_score=0.5,
        worst_metric="disconnection_cnt",
        total_recent_offline_sec=3600.0,
        importance_multiplier=1.0,
    )
    qa = QualityAssessment(
        gateway_id=gw,
        is_eligible=True,
        is_full_quality=True,
        confidence_penalty=0.0,
        reference_days_count=21,
        detection_days_count=7,
    )

    mf_missing = MeterImpactFeatures(
        gateway_id=gw,
        meters_expected=0,
        meters_read=0,
        read_success_ratio=1.0,
        degradation_vs_history=0.0,
        exposure_meters=100,
        has_meter_data=False,
    )

    scored_list = ranker.score_gateways({gw: tf}, {gw: mf_missing}, {gw: qa})
    assert len(scored_list) == 1
    scored = scored_list[0]

    assert scored.meter_impact == 0.0
    assert scored.final_score > 0.0

    # Final score should be based on re-normalized telemetry and confidence weights
    expected_norm = (
        (0.70 / 0.75) * scored.telemetry_risk + (0.05 / 0.75) * scored.data_confidence
    )
    assert abs(scored.final_score - expected_norm) < 0.01


def test_degraded_coverage_incurs_confidence_penalty(test_config: AppConfig):
    """Verify degraded telemetry history receives a confidence penalty."""
    ranker = RiskRanker(test_config)
    gw = "020000000001"

    tf = TelemetryFeatures(
        gateway_id=gw,
        flagged_hours=10,
        total_detection_hours=168,
        persistence_ratio=10 / 168,
        avg_anomaly_severity=3.0,
        max_anomaly_severity=4.0,
        recency_score=0.5,
        worst_metric="disconnection_cnt",
        total_recent_offline_sec=1000.0,
        importance_multiplier=1.0,
    )
    mf = MeterImpactFeatures(
        gateway_id=gw,
        meters_expected=100,
        meters_read=100,
        read_success_ratio=1.0,
        degradation_vs_history=0.0,
        exposure_meters=100,
        has_meter_data=True,
    )

    # Full quality assessment
    qa_full = QualityAssessment(
        gateway_id=gw,
        is_eligible=True,
        is_full_quality=True,
        confidence_penalty=0.0,
        reference_days_count=21,
        detection_days_count=7,
    )
    score_full = ranker.score_single(tf, mf, qa_full)

    # Degraded quality assessment (e.g. only 10 days reference, 4 days detection)
    qa_degraded = QualityAssessment(
        gateway_id=gw,
        is_eligible=True,
        is_full_quality=False,
        confidence_penalty=0.35,
        reference_days_count=10,
        detection_days_count=4,
    )
    score_degraded = ranker.score_single(tf, mf, qa_degraded)

    assert score_full > score_degraded
    assert ranker.compute_data_confidence(qa_degraded, mf) < ranker.compute_data_confidence(qa_full, mf)
