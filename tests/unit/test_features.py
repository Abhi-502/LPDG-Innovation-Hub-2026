"""Unit tests for feature builder and robust statistics."""

from __future__ import annotations

import datetime as dt
import numpy as np
import pandas as pd
import pytest

from app.config import AppConfig
from app.features.builder import FeatureBuilder, compute_median_mad


def test_compute_median_mad_clean():
    s = pd.Series([10.0, 10.0, 10.0, 10.0, 10.0, 20.0])
    med, scale = compute_median_mad(s, min_scale_floor=1.0)
    assert med == 10.0
    assert scale >= 1.0


def test_compute_median_mad_empty():
    s = pd.Series([], dtype=float)
    med, scale = compute_median_mad(s, min_scale_floor=2.0)
    assert med == 0.0
    assert scale == 2.0


def test_feature_builder_telemetry_isolation(test_config: AppConfig):
    fb = FeatureBuilder(test_config)
    cutoff = pd.Timestamp("2026-03-23 00:00:00", tz="UTC")

    # Generate synthetic telemetry with spike in detection window
    timestamps = pd.date_range(start=cutoff - pd.Timedelta(days=28), end=cutoff - pd.Timedelta(hours=1), freq="1h", tz="UTC")
    rows = []
    gw = "020000000001"
    for ts in timestamps:
        # High offline in last 7 days only
        is_det = ts >= cutoff - pd.Timedelta(days=7)
        rows.append(
            {
                "gateway_id": gw,
                "ts": ts,
                "offline_duration_sec": 3600.0 if is_det else 10.0,
                "disconnection_cnt": 5 if is_det else 0,
                "reboot_cnt": 0,
            }
        )
    tel_df = pd.DataFrame(rows)

    feats = fb.extract_telemetry_features(tel_df, cutoff_utc=cutoff, eligible_gateways={gw})
    assert gw in feats
    tf = feats[gw]
    assert tf.flagged_hours > 0
    assert tf.persistence_ratio > 0.0
    assert tf.avg_anomaly_severity > 0.0
    assert tf.worst_metric in ["offline_duration_sec", "disconnection_cnt"]
