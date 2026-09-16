"""Unit tests for ranking strategy implementations."""

from __future__ import annotations

import pytest
from app.config import AppConfig
from app.domain.errors import InvalidRequestError
from app.domain.models import (
    MeterImpactFeatures,
    QualityAssessment,
    ScoredGateway,
    TelemetryFeatures,
)
from app.ranking.base import get_ranking_strategy
from app.ranking.baseline import Baseline3SigmaRanker
from app.ranking.risk_v1 import RiskRanker


def test_strategy_factory(test_config: AppConfig):
    strat1 = get_ranking_strategy("risk_v1", test_config)
    assert isinstance(strat1, RiskRanker)
    assert strat1.name == "risk_v1"

    strat2 = get_ranking_strategy("baseline", test_config)
    assert isinstance(strat2, Baseline3SigmaRanker)
    assert strat2.name == "baseline"

    with pytest.raises(InvalidRequestError):
        get_ranking_strategy("non_existent_strategy", test_config)


def test_risk_ranker_scoring(test_config: AppConfig):
    ranker = RiskRanker(test_config)

    tf = TelemetryFeatures(
        gateway_id="020000000001",
        flagged_hours=20,
        total_detection_hours=168,
        persistence_ratio=20 / 168,
        avg_anomaly_severity=5.0,
        max_anomaly_severity=8.0,
        recency_score=0.8,
        worst_metric="offline_duration_sec",
        total_recent_offline_sec=50000.0,
        importance_multiplier=1.0,
    )
    mf = MeterImpactFeatures(
        gateway_id="020000000001",
        meters_expected=200,
        meters_read=160,
        read_success_ratio=0.8,
        degradation_vs_history=0.15,
        exposure_meters=200,
        has_meter_data=True,
    )
    qa = QualityAssessment(
        gateway_id="020000000001",
        is_eligible=True,
        is_full_quality=True,
        confidence_penalty=0.0,
        reference_days_count=21,
        detection_days_count=7,
    )

    score = ranker.score_single(tf, mf, qa)
    assert 0.0 <= score <= 100.0
    assert score > 0.0


def test_risk_ranker_deterministic_sorting(test_config: AppConfig):
    ranker = RiskRanker(test_config)

    g1 = ScoredGateway(
        gateway_id="020000000001",
        final_score=80.0,
        telemetry_risk=80.0,
        meter_impact=80.0,
        data_confidence=100.0,
        telemetry_features=TelemetryFeatures("020000000001", 10, 168, 0.1, 4.0, 5.0, 0.5, "offline_duration_sec", 1000.0),
        meter_features=MeterImpactFeatures("020000000001", 100, 90, 0.9, 0.1, 100, True),
        quality_assessment=QualityAssessment("020000000001", True, True, 0.0, 21, 7),
    )
    g2 = ScoredGateway(
        gateway_id="020000000002",
        final_score=90.0,
        telemetry_risk=90.0,
        meter_impact=90.0,
        data_confidence=100.0,
        telemetry_features=TelemetryFeatures("020000000002", 15, 168, 0.15, 5.0, 6.0, 0.7, "offline_duration_sec", 2000.0),
        meter_features=MeterImpactFeatures("020000000002", 150, 120, 0.8, 0.2, 150, True),
        quality_assessment=QualityAssessment("020000000002", True, True, 0.0, 21, 7),
    )

    ranked = ranker.rank_gateways([g1, g2], visit_limit=2)
    assert ranked[0].gateway_id == "020000000002"
    assert ranked[1].gateway_id == "020000000001"
