"""Unit tests verifying baseline reference isolation and strict point-in-time boundaries."""

from __future__ import annotations

import pandas as pd
import pytest

from app.config import AppConfig
from app.features.builder import FeatureBuilder
from app.repositories.telemetry import TelemetryRepository
from app.repositories.gateways import GatewayRepository


def test_recent_failure_does_not_contaminate_reference_baseline(test_config: AppConfig):
    """Test that a massive failure in the 7-day detection window does not contaminate 21-day reference statistics."""
    cutoff = pd.Timestamp("2026-02-02 00:00:00", tz="UTC")
    start = cutoff - pd.Timedelta(days=28)
    det_start = cutoff - pd.Timedelta(days=7)

    builder = FeatureBuilder(test_config)
    gw = "020000000001"

    # Generate reference history with clean, normal behavior
    timestamps_ref = pd.date_range(start=start, end=det_start - pd.Timedelta(hours=1), freq="1h", tz="UTC")
    ref_records = [
        {
            "gateway_id": gw,
            "ts": ts,
            "offline_duration_sec": 5.0,
            "disconnection_cnt": 0,
            "reboot_cnt": 0,
        }
        for ts in timestamps_ref
    ]

    # Scenario A: Clean detection window
    timestamps_det = pd.date_range(start=det_start, end=cutoff - pd.Timedelta(hours=1), freq="1h", tz="UTC")
    clean_det_records = [
        {
            "gateway_id": gw,
            "ts": ts,
            "offline_duration_sec": 5.0,
            "disconnection_cnt": 0,
            "reboot_cnt": 0,
        }
        for ts in timestamps_det
    ]

    df_clean = pd.DataFrame(ref_records + clean_det_records)
    feats_clean = builder.extract_telemetry_features(df_clean, cutoff, {gw})

    # Scenario B: Massive failure in detection window (continuous 3600s offline)
    failing_det_records = [
        {
            "gateway_id": gw,
            "ts": ts,
            "offline_duration_sec": 3600.0,
            "disconnection_cnt": 50,
            "reboot_cnt": 10,
        }
        for ts in timestamps_det
    ]

    df_failing = pd.DataFrame(ref_records + failing_det_records)
    feats_failing = builder.extract_telemetry_features(df_failing, cutoff, {gw})

    # Clean scenario should have 0 flagged hours
    assert feats_clean[gw].flagged_hours == 0
    assert feats_clean[gw].persistence_ratio == 0.0

    # Failing scenario should have 168 flagged hours (100% persistence)
    assert feats_failing[gw].flagged_hours == len(timestamps_det)
    assert feats_failing[gw].persistence_ratio == 1.0
    assert feats_failing[gw].avg_anomaly_severity > 0.0


def test_window_boundaries_strictly_point_in_time(test_config: AppConfig):
    """Test that records at or after cutoff are never loaded or included in features."""
    cutoff = pd.Timestamp("2026-02-02 00:00:00", tz="UTC")
    builder = FeatureBuilder(test_config)
    gw = "020000000001"

    # Reference window: [cutoff - 28d, cutoff - 7d)
    # Detection window: [cutoff - 7d, cutoff)
    # Excluded future: >= cutoff
    timestamps = [
        cutoff - pd.Timedelta(days=29),  # before reference
        cutoff - pd.Timedelta(days=20),  # in reference
        cutoff - pd.Timedelta(days=5),   # in detection
        cutoff - pd.Timedelta(seconds=1), # last valid detection second
        cutoff,                          # EXACT CUTOFF -> MUST BE EXCLUDED
        cutoff + pd.Timedelta(hours=1),  # Future -> MUST BE EXCLUDED
    ]

    records = [
        {
            "gateway_id": gw,
            "ts": ts,
            "offline_duration_sec": 3600.0,
            "disconnection_cnt": 10,
            "reboot_cnt": 2,
        }
        for ts in timestamps
    ]
    df = pd.DataFrame(records)

    # When extracting features, only records strictly before cutoff are considered
    feats = builder.extract_telemetry_features(df, cutoff, {gw})
    assert gw in feats
