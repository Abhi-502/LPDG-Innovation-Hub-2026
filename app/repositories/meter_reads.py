"""Meter read success repository."""

from __future__ import annotations

import datetime as dt
import logging
import pathlib
import pandas as pd

from app.config import AppConfig
from app.repositories.gateways import normalise_gateway_id

logger = logging.getLogger(__name__)


class MeterReadRepository:
    """Repository accessing meter_read_success.csv with point-in-time constraints."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @property
    def file_path(self) -> pathlib.Path:
        return self.config.data_dir / "meter_read_success.csv"

    def exists_on_disk(self) -> bool:
        return self.file_path.exists()

    def load_meter_reads(
        self,
        cutoff_date: dt.date,
        lookback_weeks: int = 4,
    ) -> pd.DataFrame:
        """Load meter_read_success.csv up to reporting week strictly before cutoff."""
        if not self.file_path.exists():
            logger.warning("meter_read_success.csv not found at %s", self.file_path)
            return pd.DataFrame(columns=["week_start", "gateway_id", "meters_expected", "meters_read"])

        try:
            df = pd.read_csv(self.file_path)
        except Exception as e:
            logger.error("Failed reading meter read success file: %s", e)
            return pd.DataFrame(columns=["week_start", "gateway_id", "meters_expected", "meters_read"])

        df["week_start"] = pd.to_datetime(df["week_start"]).dt.date
        df["gateway_id"] = df["gateway_id"].apply(normalise_gateway_id)
        df = df.dropna(subset=["gateway_id"])

        # Point-in-time filter: week_start < cutoff_date
        min_week = cutoff_date - dt.timedelta(weeks=lookback_weeks)
        mask = (df["week_start"] < cutoff_date) & (df["week_start"] >= min_week)
        df = df[mask].copy()

        df["meters_expected"] = pd.to_numeric(df["meters_expected"], errors="coerce").fillna(0).astype(int)
        df["meters_read"] = pd.to_numeric(df["meters_read"], errors="coerce").fillna(0).astype(int)

        return df
