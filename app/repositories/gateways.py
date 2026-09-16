"""Gateway Master repository for fleet metadata."""

from __future__ import annotations

import datetime as dt
import logging
import pathlib
import re
from typing import Dict, Optional
import pandas as pd

from app.config import AppConfig
from app.domain.errors import DataUnavailableError
from app.domain.models import GatewayMaster

logger = logging.getLogger(__name__)

_BARE = re.compile(r"^[0-9A-Fa-f]{12}$")
_COLON = re.compile(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")


def normalise_gateway_id(value: str | None) -> Optional[str]:
    """Normalise gateway ID to uppercase 12-character hex format."""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if _BARE.match(text):
        return text.upper()
    if _COLON.match(text):
        return text.replace(":", "").upper()
    return None


class GatewayRepository:
    """Repository accessing gateway_master.csv with cached read support."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._cache: Optional[pd.DataFrame] = None
        self._records: Optional[Dict[str, GatewayMaster]] = None

    @property
    def file_path(self) -> pathlib.Path:
        return self.config.data_dir / "gateway_master.csv"

    def exists_on_disk(self) -> bool:
        return self.file_path.exists()

    def load_master(self, force_reload: bool = False) -> pd.DataFrame:
        """Load and normalise gateway master records."""
        if self._cache is not None and not force_reload:
            return self._cache.copy()

        if not self.file_path.exists():
            raise DataUnavailableError(f"Gateway master file not found at {self.file_path}")

        try:
            df = pd.read_csv(
                self.file_path,
                usecols=[
                    "gateway_id",
                    "tenant",
                    "site_type",
                    "region",
                    "hw_model",
                    "installed_on",
                    "decommissioned_on",
                    "n_meters_installed",
                ],
                encoding="utf-8",
                encoding_errors="replace",
            )
        except Exception as e:
            raise DataUnavailableError(f"Failed to read gateway master from {self.file_path}: {e}") from e

        df["gateway_id_norm"] = df["gateway_id"].apply(normalise_gateway_id)
        invalid_count = int(df["gateway_id_norm"].isna().sum())
        if invalid_count > 0:
            logger.warning("Dropped %d invalid gateway IDs from gateway_master", invalid_count)
            df = df.dropna(subset=["gateway_id_norm"])

        df["gateway_id"] = df["gateway_id_norm"]
        df["installed_on"] = pd.to_datetime(df["installed_on"]).dt.date
        df["decommissioned_on"] = pd.to_datetime(df["decommissioned_on"]).dt.date
        df["n_meters_installed"] = (
            pd.to_numeric(df["n_meters_installed"], errors="coerce").fillna(0).astype(int)
        )

        cleaned_df = df.drop(columns=["gateway_id_norm"])
        self._cache = cleaned_df

        # Populate internal lookup map
        records: Dict[str, GatewayMaster] = {}
        for _, row in cleaned_df.iterrows():
            gw = str(row["gateway_id"])
            decom = row["decommissioned_on"] if pd.notna(row["decommissioned_on"]) else None
            records[gw] = GatewayMaster(
                gateway_id=gw,
                tenant=str(row.get("tenant", "")),
                site_type=str(row.get("site_type", "")),
                region=str(row.get("region", "")),
                hw_model=str(row.get("hw_model", "")),
                installed_on=row["installed_on"],
                decommissioned_on=decom,
                n_meters_installed=int(row["n_meters_installed"]),
            )
        self._records = records

        return cleaned_df.copy()

    def get_gateway(self, gateway_id: str) -> Optional[GatewayMaster]:
        """Fetch single gateway master record."""
        norm_id = normalise_gateway_id(gateway_id)
        if norm_id is None:
            return None
        if self._records is None:
            self.load_master()
        assert self._records is not None
        return self._records.get(norm_id)

    def exists(self, gateway_id: str) -> bool:
        """Check if gateway exists in master records."""
        return self.get_gateway(gateway_id) is not None
