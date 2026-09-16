"""Integration tests for FastAPI endpoints."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_health_endpoint(test_client: TestClient):
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ["healthy", "degraded"]
    assert data["data_dir_ready"] is True
    assert "version" in data


def test_get_predictions_endpoint(test_client: TestClient):
    response = test_client.get("/api/v1/weeks/2026-03-23/predictions")
    assert response.status_code == 200
    data = response.json()
    assert data["week_start"] == "2026-03-23"
    assert data["count"] == 15
    assert len(data["predictions"]) == 15
    assert data["predictions"][0]["rank"] == 1


def test_get_predictions_invalid_date(test_client: TestClient):
    response = test_client.get("/api/v1/weeks/2026-99-99/predictions")
    assert response.status_code == 400


def test_get_predictions_unsupported_week(test_client: TestClient):
    response = test_client.get("/api/v1/weeks/2026-05-04/predictions")
    assert response.status_code == 404


def test_get_gateway_ranked_endpoint(test_client: TestClient):
    # First get top gateway
    preds_res = test_client.get("/api/v1/weeks/2026-03-23/predictions")
    top_gw = preds_res.json()["predictions"][0]["gateway_id"]

    gw_res = test_client.get(f"/api/v1/weeks/2026-03-23/gateways/{top_gw}")
    assert gw_res.status_code == 200
    data = gw_res.json()
    assert data["gateway_id"] == top_gw
    assert data["status"] == "RANKED_TOP_15"
    assert data["rank"] == 1


def test_get_gateway_ineligible_endpoint(test_client: TestClient):
    # Decommissioned gateway 25 (0x19)
    gw_res = test_client.get("/api/v1/weeks/2026-03-23/gateways/020000000019")
    assert gw_res.status_code == 200
    data = gw_res.json()
    assert data["status"] == "INELIGIBLE"
    assert data["rank"] is None
    assert data["is_eligible"] is False


def test_get_gateway_unknown_endpoint(test_client: TestClient):
    gw_res = test_client.get("/api/v1/weeks/2026-03-23/gateways/020000000099")
    assert gw_res.status_code == 404


def test_runs_endpoint_create_and_get(test_client: TestClient):
    create_res = test_client.post(
        "/api/v1/runs",
        json={"weeks": ["2026-03-16", "2026-03-23"], "ranking_method": "risk_v1"},
    )
    assert create_res.status_code == 201
    run_data = create_res.json()
    run_id = run_data["run_id"]
    assert run_data["status"] == "SUCCEEDED"

    # Query run status
    get_res = test_client.get(f"/api/v1/runs/{run_id}")
    assert get_res.status_code == 200
    assert get_res.json()["run_id"] == run_id
