"""Unit tests for deterministic 4-key tie breaking."""

from __future__ import annotations

import pytest

from app.config import AppConfig
from app.domain.models import (
    MeterImpactFeatures,
    QualityAssessment,
    ScoredGateway,
    TelemetryFeatures,
)
from app.ranking.risk_v1 import RiskRanker


def test_deterministic_tie_breaks(test_config: AppConfig):
    ranker = RiskRanker(test_config)

    # Two gateways with EXACT same score, but g1 has more connected meters
    g1 = ScoredGateway(
        gateway_id="020000000001",
        final_score=85.0,
        telemetry_risk=85.0,
        meter_impact=85.0,
        data_confidence=100.0,
        telemetry_features=TelemetryFeatures("020000000001", 10, 168, 0.1, 4.0, 5.0, 0.5, "offline_duration_sec", 1000.0),
        meter_features=MeterImpactFeatures("020000000001", 500, 400, 0.8, 0.2, 500, True),
        quality_assessment=QualityAssessment("020000000001", True, True, 0.0, 21, 7),
    )
    g2 = ScoredGateway(
        gateway_id="020000000002",
        final_score=85.0,
        telemetry_risk=85.0,
        meter_impact=85.0,
        data_confidence=100.0,
        telemetry_features=TelemetryFeatures("020000000002", 10, 168, 0.1, 4.0, 5.0, 0.5, "offline_duration_sec", 1000.0),
        meter_features=MeterImpactFeatures("020000000002", 200, 160, 0.8, 0.2, 200, True),
        quality_assessment=QualityAssessment("020000000002", True, True, 0.0, 21, 7),
    )

    ranked = ranker.rank_gateways([g2, g1], visit_limit=2)
    # g1 must rank first because exposure_meters (500 > 200)
    assert ranked[0].gateway_id == "020000000001"
    assert ranked[1].gateway_id == "020000000002"
