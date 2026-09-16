"""Feature engineering for gateway telemetry and meter-read impact.

Enforces strictly separated 21-day historical reference windows and 7-day
detection windows. Computes robust non-parametric statistics (Median & MAD),
severity, persistence, recency, and meter-read degradation.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Dict, Set, Tuple
import numpy as np
import pandas as pd

from app.config import AppConfig
from app.domain.models import MeterImpactFeatures, TelemetryFeatures

logger = logging.getLogger(__name__)


def compute_median_mad(
    series: pd.Series,
    scale_factor: float = 1.4826,
    min_scale_floor: float = 1.0,
    epsilon: float = 1e-4,
) -> Tuple[float, float]:
    """Compute robust location (median) and scale (MAD) safely."""
    clean = series.dropna()
    if clean.empty:
        return 0.0, max(min_scale_floor, epsilon)
    med = float(clean.median())
    abs_dev = (clean - med).abs()
    mad = float(abs_dev.median())
    scale = mad * scale_factor
    if scale < epsilon:
        std = float(clean.std(ddof=0))
        scale = max(std, min_scale_floor, epsilon)
    else:
        scale = max(scale, min_scale_floor)
    return med, scale


class FeatureBuilder:
    """Constructs point-in-time features with strict baseline isolation."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def extract_telemetry_features(
        self,
        telemetry_df: pd.DataFrame,
        cutoff_utc: pd.Timestamp,
        eligible_gateways: Set[str],
    ) -> Dict[str, TelemetryFeatures]:
        """Extract isolated baseline and detection features per gateway."""
        ref_start = cutoff_utc - pd.Timedelta(days=self.config.total_trailing_days)
        det_start = cutoff_utc - pd.Timedelta(days=self.config.detection_days)

        # Slice strictly separated half-open windows
        ref_mask = (telemetry_df["ts"] >= ref_start) & (telemetry_df["ts"] < det_start)
        det_mask = (telemetry_df["ts"] >= det_start) & (telemetry_df["ts"] < cutoff_utc)

        ref_df = telemetry_df[ref_mask]
        det_df = telemetry_df[det_mask]

        # Compute reference statistics per gateway
        ref_stats: Dict[str, Dict[str, Tuple[float, float]]] = {}
        for gw, group in ref_df.groupby("gateway_id"):
            ref_stats[gw] = {}
            for metric in self.config.telemetry_metrics:
                min_floor = self.config.metric_min_scales.get(metric, 1.0)
                if metric in group.columns:
                    ref_stats[gw][metric] = compute_median_mad(
                        group[metric],
                        scale_factor=self.config.mad_scale_factor,
                        min_scale_floor=min_floor,
                        epsilon=self.config.min_scale_epsilon,
                    )
                else:
                    ref_stats[gw][metric] = (0.0, min_floor)

        features: Dict[str, TelemetryFeatures] = {}
        det_grouped = det_df.groupby("gateway_id")

        for gw in eligible_gateways:
            gw_stats = ref_stats.get(gw, {})
            gw_det = det_grouped.get_group(gw) if gw in det_grouped.groups else pd.DataFrame()

            if gw_det.empty:
                features[gw] = TelemetryFeatures(
                    gateway_id=gw,
                    flagged_hours=0,
                    total_detection_hours=0,
                    persistence_ratio=0.0,
                    avg_anomaly_severity=0.0,
                    max_anomaly_severity=0.0,
                    recency_score=0.0,
                    worst_metric="none",
                    total_recent_offline_sec=0.0,
                    importance_multiplier=1.0,
                )
                continue

            n_det_hours = len(gw_det)
            flagged_hour_mask = pd.Series(False, index=gw_det.index)
            max_severities = pd.Series(0.0, index=gw_det.index)
            metric_breaches: Dict[str, int] = {m: 0 for m in self.config.telemetry_metrics}

            for metric in self.config.telemetry_metrics:
                if metric not in gw_det.columns:
                    continue
                min_floor = self.config.metric_min_scales.get(metric, 1.0)
                med, scale = gw_stats.get(metric, (0.0, min_floor))
                z = (gw_det[metric] - med) / scale
                z_capped = z.clip(lower=0.0, upper=self.config.max_severity_cap)
                is_anom = z > self.config.anomaly_threshold_sigma
                flagged_hour_mask = flagged_hour_mask | is_anom
                max_severities = np.maximum(max_severities, z_capped)
                metric_breaches[metric] = int(is_anom.sum())

            flagged_count = int(flagged_hour_mask.sum())
            persistence_ratio = flagged_count / max(1, n_det_hours)

            if flagged_count > 0:
                flagged_severities = max_severities[flagged_hour_mask]
                avg_sev = float(flagged_severities.mean())
                max_sev = float(flagged_severities.max())
                worst_metric = max(metric_breaches, key=metric_breaches.get)
                if metric_breaches[worst_metric] == 0:
                    worst_metric = "none"
            else:
                avg_sev = 0.0
                max_sev = 0.0
                worst_metric = "none"

            # Exponential decay recency weighting (half-life 48 hours)
            hour_deltas = (cutoff_utc - gw_det["ts"]).dt.total_seconds() / 3600.0
            weights = np.exp(-hour_deltas / 48.0)
            if flagged_count > 0:
                anom_weights = weights[flagged_hour_mask]
                recency_score = float(anom_weights.sum() / max(1e-6, weights.sum()))
            else:
                recency_score = 0.0

            offline_sec = (
                float(gw_det["offline_duration_sec"].sum())
                if "offline_duration_sec" in gw_det.columns
                else 0.0
            )

            imp_mult = 1.0
            for imp_col in self.config.importance_metrics:
                if imp_col in gw_det.columns:
                    val = gw_det[imp_col].dropna()
                    if not val.empty and val.max() > 0:
                        imp_mult = max(imp_mult, 1.0 + min(0.15, float(val.mean()) / 10.0))

            features[gw] = TelemetryFeatures(
                gateway_id=gw,
                flagged_hours=flagged_count,
                total_detection_hours=n_det_hours,
                persistence_ratio=persistence_ratio,
                avg_anomaly_severity=avg_sev,
                max_anomaly_severity=max_sev,
                recency_score=min(1.0, recency_score),
                worst_metric=worst_metric,
                total_recent_offline_sec=offline_sec,
                importance_multiplier=imp_mult,
            )

        return features

    def extract_meter_impact_features(
        self,
        meter_df: pd.DataFrame,
        master_df: pd.DataFrame,
        cutoff_date: dt.date,
        eligible_gateways: Set[str],
    ) -> Dict[str, MeterImpactFeatures]:
        """Compute meter-read success and degradation features."""
        installed_map = master_df.set_index("gateway_id")["n_meters_installed"].to_dict()
        features: Dict[str, MeterImpactFeatures] = {}

        if meter_df.empty:
            for gw in eligible_gateways:
                exp = installed_map.get(gw, 0)
                features[gw] = MeterImpactFeatures(
                    gateway_id=gw,
                    meters_expected=exp,
                    meters_read=exp,
                    read_success_ratio=1.0,
                    degradation_vs_history=0.0,
                    exposure_meters=exp,
                    has_meter_data=False,
                )
            return features

        latest_idx = meter_df.groupby("gateway_id")["week_start"].idxmax()
        recent_records = meter_df.loc[latest_idx].set_index("gateway_id")

        hist_df = meter_df.drop(index=latest_idx)
        hist_means: Dict[str, float] = {}
        if not hist_df.empty:
            valid_hist = hist_df[hist_df["meters_expected"] > 0].copy()
            valid_hist["ratio"] = valid_hist["meters_read"] / valid_hist["meters_expected"]
            hist_means = valid_hist.groupby("gateway_id")["ratio"].mean().to_dict()

        for gw in eligible_gateways:
            exp_master = installed_map.get(gw, 0)
            if gw in recent_records.index:
                row = recent_records.loc[gw]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[-1]
                m_exp = int(row["meters_expected"])
                m_read = int(row["meters_read"])
                ratio = max(0.0, min(1.0, m_read / m_exp)) if m_exp > 0 else 1.0
                hist_ratio = hist_means.get(gw, 0.95)
                degradation = max(0.0, hist_ratio - ratio)
                exposure = max(m_exp, exp_master)
                has_data = True
            else:
                m_exp = exp_master
                m_read = exp_master
                ratio = 1.0
                degradation = 0.0
                exposure = exp_master
                has_data = False

            features[gw] = MeterImpactFeatures(
                gateway_id=gw,
                meters_expected=m_exp,
                meters_read=m_read,
                read_success_ratio=ratio,
                degradation_vs_history=degradation,
                exposure_meters=exposure,
                has_meter_data=has_data,
            )

        return features
