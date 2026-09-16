"""Integration tests for GatewayService."""

from __future__ import annotations

import datetime as dt
import pytest

from app.config import AppConfig
from app.domain.errors import GatewayNotFoundError
from app.domain.models import GatewayStatus
from app.services.gateway_service import GatewayService
from app.services.ranking_service import RankingService


def test_evaluate_known_gateway_ranked_top15(test_config: AppConfig):
    ranking_svc = RankingService(test_config)
    gw_svc = GatewayService(test_config, ranking_svc)

    monday = dt.date(2026, 3, 23)
    top15 = ranking_svc.get_top_ranked_gateways(monday)
    top_gw_id = top15[0].gateway_id

    res = gw_svc.evaluate_gateway(monday, top_gw_id)
    assert res.status == GatewayStatus.RANKED_TOP_15
    assert res.rank == 1
    assert res.score is not None
    assert res.is_eligible is True
    assert "details" in res.model_dump()


def test_evaluate_known_gateway_eligible_unranked(test_config: AppConfig):
    ranking_svc = RankingService(test_config)
    gw_svc = GatewayService(test_config, ranking_svc)

    monday = dt.date(2026, 3, 23)
    # Gateway 20 in our generator is eligible but ranked below top 15
    res = gw_svc.evaluate_gateway(monday, "020000000014")
    assert res.is_eligible is True
    assert res.score is not None


def test_evaluate_ineligible_gateway(test_config: AppConfig):
    ranking_svc = RankingService(test_config)
    gw_svc = GatewayService(test_config, ranking_svc)

    monday = dt.date(2026, 3, 23)
    # Gateway 25 in generator is decommissioned
    res = gw_svc.evaluate_gateway(monday, "020000000019")  # 25 in hex is 0x19
    assert res.status == GatewayStatus.INELIGIBLE
    assert res.rank is None
    assert res.score is None
    assert res.is_eligible is False
    assert "Ineligible" in res.reason


def test_evaluate_unknown_gateway_raises_404(test_config: AppConfig):
    ranking_svc = RankingService(test_config)
    gw_svc = GatewayService(test_config, ranking_svc)

    monday = dt.date(2026, 3, 23)
    with pytest.raises(GatewayNotFoundError):
        gw_svc.evaluate_gateway(monday, "020000000099")
