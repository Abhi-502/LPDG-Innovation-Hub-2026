"""Telemetry repository for point-in-time Parquet access."""

from __future__ import annotations

import logging
import pathlib
from typing import List, Optional
import pandas as pd

from app.config import AppConfig
from app.domain.errors import DataUnavailableError
from app.repositories.gateways import normalise_gateway_id

logger = logging.getLogger(__name__)


class TelemetryRepository:
    """Repository managing point-in-time partitioned Parquet telemetry data."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    @property
    def dir_path(self) -> pathlib.Path:
        return self.config.data_dir / "telemetry"

    def exists_on_disk(self) -> bool:
        return self.dir_path.exists() and self.dir_path.is_dir()

    def load_telemetry(
        self,
        cutoff_utc: pd.Timestamp,
        trailing_days: int = 28,
        required_metrics: Optional[List[str]] = None,
        importance_metrics: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Load telemetry records strictly within [cutoff - trailing_days, cutoff)."""
        if not self.dir_path.exists():
            raise DataUnavailableError(f"Telemetry directory not found at {self.dir_path}")

        start_utc = cutoff_utc - pd.Timedelta(days=trailing_days)
        metrics = required_metrics or list(self.config.telemetry_metrics)
        opt_metrics = importance_metrics or list(self.config.importance_metrics)

        start_month = start_utc.strftime("%Y-%m")
        end_month = cutoff_utc.strftime("%Y-%m")

        month_dirs = sorted([d for d in self.dir_path.glob("month=*") if d.is_dir()])
        target_files: List[pathlib.Path] = []
        for d in month_dirs:
            m_str = d.name.replace("month=", "")
            if start_month <= m_str <= end_month:
                target_files.extend(sorted(d.glob("*.parquet")))

        if not target_files:
            target_files = sorted(self.dir_path.rglob("*.parquet"))

        if not target_files:
            logger.warning("No telemetry parquet files found under %s", self.dir_path)
            return pd.DataFrame(columns=["gateway_id", "ts", *metrics])

        cols_to_load = ["gateway_id", "ts_utc"] + [m for m in metrics]

        # Check existing columns in schema
        try:
            import pyarrow.parquet as pq
            schema = pq.read_schema(target_files[0])
            available_cols = set(schema.names)
            cols_to_load += [m for m in opt_metrics if m in available_cols]
            cols_to_load = [c for c in cols_to_load if c in available_cols]
        except Exception:
            pass

        try:
            df = pd.read_parquet(target_files, columns=list(set(cols_to_load)))
        except Exception as e:
            raise DataUnavailableError(f"Failed to read parquet telemetry files: {e}") from e

        if df.empty:
            return pd.DataFrame(columns=["gateway_id", "ts", *metrics])

        df["ts"] = pd.to_datetime(df["ts_utc"], utc=True)
        # Strictly [start_utc, cutoff_utc)
        mask = (df["ts"] >= start_utc) & (df["ts"] < cutoff_utc)
        df = df[mask].copy()

        df["gateway_id"] = df["gateway_id"].apply(normalise_gateway_id)
        df = df.dropna(subset=["gateway_id"])

        return df
