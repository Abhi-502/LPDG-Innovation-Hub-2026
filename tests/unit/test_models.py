"""Unit tests for domain models and serialization."""

from __future__ import annotations

import datetime as dt
import pytest
from pydantic import ValidationError

from app.domain.models import (
    GatewayEvaluationResponse,
    GatewayMaster,
    GatewayStatus,
    PredictionItem,
    RunResponse,
    RunStatus,
    WeeklyPredictionsResponse,
)


def test_gateway_master_model():
    gw = GatewayMaster(
        gateway_id="020000000001",
        tenant="tenant_a",
        site_type="Schaltschrank",
        region="Bayern",
        hw_model="GW-2100",
        installed_on=dt.date(2023, 1, 1),
        decommissioned_on=None,
        n_meters_installed=150,
    )
    assert gw.gateway_id == "020000000001"
    assert gw.n_meters_installed == 150
    assert gw.decommissioned_on is None


def test_prediction_item_valid():
    item = PredictionItem(
        rank=1,
        gateway_id="0202CB0A6B1F",
        score=95.5,
        reason="High priority: 24 abnormal hours.",
        ranking_method="risk_v1",
    )
    assert item.rank == 1
    assert item.score == 95.5
    assert item.ranking_method == "risk_v1"


def test_prediction_item_invalid_rank():
    with pytest.raises(ValidationError):
        PredictionItem(
            rank=16,  # max is 15
            gateway_id="0202CB0A6B1F",
            score=95.5,
            reason="High priority",
            ranking_method="risk_v1",
        )


def test_weekly_predictions_response():
    resp = WeeklyPredictionsResponse(
        week_start="2026-03-23",
        ranking_method="risk_v1",
        run_id="run_123",
        count=1,
        predictions=[
            PredictionItem(
                rank=1,
                gateway_id="0202CB0A6B1F",
                score=90.0,
                reason="Test reason",
                ranking_method="risk_v1",
            )
        ],
    )
    assert resp.count == 1
    assert resp.predictions[0].gateway_id == "0202CB0A6B1F"


def test_run_response():
    run = RunResponse(
        run_id="run_123",
        status=RunStatus.SUCCEEDED,
        ranking_method="risk_v1",
        requested_weeks=["2026-03-23"],
        started_at="2026-03-23T10:00:00+00:00",
        completed_at="2026-03-23T10:00:05+00:00",
        artifact_paths={"predictions_csv": "/path/to/csv"},
    )
    assert run.status == RunStatus.SUCCEEDED
    assert run.artifact_paths["predictions_csv"] == "/path/to/csv"
