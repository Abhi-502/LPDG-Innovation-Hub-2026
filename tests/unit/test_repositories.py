"""Unit tests for repositories."""

from __future__ import annotations

import datetime as dt
import pandas as pd
import pytest

from app.config import AppConfig
from app.domain.errors import DataUnavailableError
from app.repositories.gateways import GatewayRepository, normalise_gateway_id
from app.repositories.meter_reads import MeterReadRepository
from app.repositories.telemetry import TelemetryRepository


def test_normalise_gateway_id():
    assert normalise_gateway_id("0202cb0a6b1f") == "0202CB0A6B1F"
    assert normalise_gateway_id("02:02:CB:0A:6B:1F") == "0202CB0A6B1F"
    assert normalise_gateway_id("02:02:cb:0a:6b:1f") == "0202CB0A6B1F"
    assert normalise_gateway_id("invalid-id") is None
    assert normalise_gateway_id(None) is None


def test_gateway_repository(test_config: AppConfig):
    repo = GatewayRepository(test_config)
    assert repo.exists_on_disk()

    df = repo.load_master()
    assert not df.empty
    assert "gateway_id" in df.columns
    assert "installed_on" in df.columns

    # Test single fetch
    gw = repo.get_gateway("020000000001")
    assert gw is not None
    assert gw.gateway_id == "020000000001"

    # Test unknown fetch
    assert repo.get_gateway("020000000099") is None


def test_telemetry_repository(test_config: AppConfig):
    repo = TelemetryRepository(test_config)
    assert repo.exists_on_disk()

    cutoff_utc = pd.Timestamp("2026-03-23 00:00:00", tz="UTC")
    df = repo.load_telemetry(cutoff_utc=cutoff_utc, trailing_days=28)

    assert not df.empty
    assert "gateway_id" in df.columns
    assert "ts" in df.columns
    # Check that ts is strictly < cutoff_utc
    assert (df["ts"] < cutoff_utc).all()


def test_meter_read_repository(test_config: AppConfig):
    repo = MeterReadRepository(test_config)
    assert repo.exists_on_disk()

    cutoff_date = dt.date(2026, 3, 23)
    df = repo.load_meter_reads(cutoff_date=cutoff_date, lookback_weeks=4)

    assert not df.empty
    assert "gateway_id" in df.columns
    assert (df["week_start"] < cutoff_date).all()


def test_missing_data_directory_raises_error(tmp_path):
    empty_config = AppConfig(data_dir=tmp_path / "non_existent_data")
    repo = GatewayRepository(empty_config)

    with pytest.raises(DataUnavailableError):
        repo.load_master()
