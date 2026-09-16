"""Unit tests for explanation generation."""

from __future__ import annotations

import datetime as dt
from app.config import AppConfig
from app.domain.models import (
    GatewayMaster,
    MeterImpactFeatures,
    QualityAssessment,
    ScoredGateway,
    TelemetryFeatures,
)
from app.explanations.builder import ExplanationBuilder


def test_ranked_reason_length(test_config: AppConfig):
    builder = ExplanationBuilder(test_config)

    gw = ScoredGateway(
        gateway_id="020000000001",
        final_score=85.0,
        telemetry_risk=90.0,
        meter_impact=80.0,
        data_confidence=100.0,
        telemetry_features=TelemetryFeatures(
            "020000000001", 24, 168, 0.14, 6.0, 8.0, 0.9, "offline_duration_sec", 40000.0
        ),
        meter_features=MeterImpactFeatures(
            "020000000001", 300, 240, 0.8, 0.15, 300, True
        ),
        quality_assessment=QualityAssessment(
            "020000000001", True, True, 0.0, 21, 7
        ),
    )

    reason = builder.build_ranked_reason(gw, rank=1)
    assert len(reason) <= 300
    assert "High priority" in reason
    assert "offline duration" in reason


def test_ineligible_reason(test_config: AppConfig):
    builder = ExplanationBuilder(test_config)

    master = GatewayMaster(
        gateway_id="020000000099",
        tenant="tenant_a",
        site_type="Schaltschrank",
        region="Bayern",
        hw_model="GW-2100",
        installed_on=dt.date(2023, 1, 1),
        decommissioned_on=dt.date(2026, 1, 1),
        n_meters_installed=50,
    )

    reason = builder.build_ineligible_reason(master, cutoff_date=dt.date(2026, 3, 23))
    assert len(reason) <= 300
    assert "Ineligible: Gateway decommissioned" in reason
