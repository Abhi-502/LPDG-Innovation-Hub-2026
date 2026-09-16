"""Integration tests for RankingService."""

from __future__ import annotations

import datetime as dt
import pytest

from app.config import AppConfig
from app.domain.errors import WeekNotSupportedError
from app.services.ranking_service import RankingService


def test_ranking_service_get_top_ranked(test_config: AppConfig):
    svc = RankingService(test_config)
    monday = dt.date(2026, 3, 23)

    top_gateways = svc.get_top_ranked_gateways(monday)
    assert len(top_gateways) == 15
    assert all(gw.final_score >= 0.0 for gw in top_gateways)

    # Predictions format
    preds = svc.get_predictions_for_week(monday)
    assert len(preds) == 15
    assert [p.rank for p in preds] == list(range(1, 16))
    assert len(set(p.gateway_id for p in preds)) == 15


def test_ranking_service_unsupported_week(test_config: AppConfig):
    svc = RankingService(test_config)
    unsupported = dt.date(2026, 5, 4)

    with pytest.raises(WeekNotSupportedError):
        svc.get_top_ranked_gateways(unsupported)
