"""Application and pipeline configuration.

Loads configuration from environment variables with defensible operational defaults.
"""

from __future__ import annotations

import datetime as dt
import os
import pathlib
from dataclasses import dataclass, field
from typing import Dict, List, Sequence


@dataclass(frozen=True)
class AppConfig:
    """Application and ranking engine configuration."""

    # Runtime Environment
    app_env: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    api_host: str = field(default_factory=lambda: os.getenv("API_HOST", "0.0.0.0"))
    api_port: int = field(default_factory=lambda: int(os.getenv("API_PORT", "8000")))
    data_dir: pathlib.Path = field(
        default_factory=lambda: pathlib.Path(os.getenv("DATA_DIR", "./data")).resolve()
    )
    artifacts_dir: pathlib.Path = field(
        default_factory=lambda: pathlib.Path(os.getenv("ARTIFACTS_DIR", "./artifacts")).resolve()
    )
    ranking_method: str = field(default_factory=lambda: os.getenv("RANKING_METHOD", "risk_v1"))
    visit_limit: int = field(default_factory=lambda: int(os.getenv("VISIT_LIMIT", "15")))
    run_lock_path: pathlib.Path = field(
        default_factory=lambda: pathlib.Path(os.getenv("RUN_LOCK_PATH", "./artifacts/.run.lock")).resolve()
    )
    run_timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("RUN_TIMEOUT_SECONDS", "300"))
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    # Scored Weeks: 8 Mondays starting from 2026-02-02
    scored_weeks: Sequence[dt.date] = field(
        default_factory=lambda: [
            dt.date(2026, 2, 2) + dt.timedelta(days=7 * i) for i in range(8)
        ]
    )

    # Constraints
    max_reason_chars: int = 300

    # Decision windows (half-open intervals [start, cutoff))
    timezone: str = "UTC"
    reference_days: int = 21
    detection_days: int = 7
    total_trailing_days: int = 28

    # Core telemetry metrics
    telemetry_metrics: Sequence[str] = field(
        default_factory=lambda: [
            "offline_duration_sec",
            "disconnection_cnt",
            "reboot_cnt",
        ]
    )

    # Secondary monitoring importance fields
    importance_metrics: Sequence[str] = field(
        default_factory=lambda: [
            "reboot_importance",
            "no_conn_importance",
        ]
    )

    # Robust statistic parameters (Median / MAD)
    mad_scale_factor: float = 1.4826
    min_scale_epsilon: float = 1e-4
    anomaly_threshold_sigma: float = 3.0
    max_severity_cap: float = 10.0

    # Metric-specific physical minimum scale floors
    metric_min_scales: Dict[str, float] = field(
        default_factory=lambda: {
            "offline_duration_sec": 60.0,  # At least 1 minute floor
            "disconnection_cnt": 1.0,     # At least 1 event floor
            "reboot_cnt": 1.0,            # At least 1 event floor
        }
    )

    # Data Quality Gates (§6)
    min_reference_dates: int = 14
    min_hours_per_date: int = 18
    min_detection_dates: int = 5
    hard_floor_reference_dates: int = 7
    hard_floor_detection_dates: int = 3

    # Scoring Weights for RiskRanker (risk_v1)
    weight_persistence: float = 0.45
    weight_severity: float = 0.35
    weight_recency: float = 0.20

    weight_telemetry_risk: float = 0.70
    weight_meter_impact: float = 0.25
    weight_data_confidence: float = 0.05

    meter_read_reporting_lag_days: int = 7


def get_config() -> AppConfig:
    """Return default application configuration."""
    return AppConfig()
