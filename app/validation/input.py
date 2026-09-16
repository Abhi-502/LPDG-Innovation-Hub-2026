"""Input validation, parameter sanitization, and data quality gates."""

from __future__ import annotations

import datetime as dt
import logging
from typing import Dict, Optional, Set
import pandas as pd

from app.config import AppConfig
from app.domain.errors import InvalidGatewayIdError, InvalidRequestError
from app.domain.models import QualityAssessment
from app.repositories.gateways import normalise_gateway_id

logger = logging.getLogger(__name__)


def validate_iso_date(value: str) -> dt.date:
    """Validate and parse ISO 8601 YYYY-MM-DD date string."""
    try:
        parsed = dt.date.fromisoformat(value.strip())
        return parsed
    except Exception as e:
        raise InvalidRequestError(f"Invalid date format '{value}'. Expected YYYY-MM-DD.") from e


def validate_hex_gateway_id(gateway_id: str) -> str:
    """Validate that gateway_id is a valid hex format and return normalized string."""
    norm = normalise_gateway_id(gateway_id)
    if norm is None:
        raise InvalidGatewayIdError(gateway_id)
    return norm


class DataQualityGate:
    """Enforces active status, coverage sufficiency, and negative counter sanitization."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def filter_active_gateways(
        self, master_df: pd.DataFrame, monday: dt.date
    ) -> Set[str]:
        """Determine active gateways as of Monday cutoff:
        installed_on < Monday and (decommissioned_on is null or >= Monday).
        """
        installed_mask = master_df["installed_on"] < monday
        decom_mask = master_df["decommissioned_on"].isna() | (master_df["decommissioned_on"] >= monday)
        active_df = master_df[installed_mask & decom_mask]
        return set(active_df["gateway_id"].unique())

    def assess_telemetry_history(
        self,
        telemetry_df: pd.DataFrame,
        active_gateway_ids: Set[str],
        cutoff_utc: pd.Timestamp,
    ) -> Dict[str, QualityAssessment]:
        """Assess reference and detection coverage per gateway (§6 rules)."""
        ref_start = cutoff_utc - pd.Timedelta(days=self.config.total_trailing_days)
        det_start = cutoff_utc - pd.Timedelta(days=self.config.detection_days)

        tel = telemetry_df.copy()
        for metric in self.config.telemetry_metrics:
            if metric in tel.columns:
                neg_mask = tel[metric] < 0
                if neg_mask.any():
                    logger.warning("Sanitizing %d negative values in metric %s", int(neg_mask.sum()), metric)
                    tel.loc[neg_mask, metric] = None

        tel["date"] = tel["ts"].dt.date
        tel["is_ref"] = (tel["ts"] >= ref_start) & (tel["ts"] < det_start)
        tel["is_det"] = (tel["ts"] >= det_start) & (tel["ts"] < cutoff_utc)

        daily_counts = (
            tel.groupby(["gateway_id", "date", "is_ref", "is_det"])
            .size()
            .reset_index(name="hours_count")
        )
        valid_days = daily_counts[daily_counts["hours_count"] >= self.config.min_hours_per_date]

        ref_days = (
            valid_days[valid_days["is_ref"]]
            .groupby("gateway_id")["date"]
            .nunique()
            .to_dict()
        )
        det_days = (
            valid_days[valid_days["is_det"]]
            .groupby("gateway_id")["date"]
            .nunique()
            .to_dict()
        )

        assessments: Dict[str, QualityAssessment] = {}

        for gw in active_gateway_ids:
            n_ref = ref_days.get(gw, 0)
            n_det = det_days.get(gw, 0)

            # Hard floor check
            if n_ref < self.config.hard_floor_reference_dates or n_det < self.config.hard_floor_detection_dates:
                assessments[gw] = QualityAssessment(
                    gateway_id=gw,
                    is_eligible=False,
                    is_full_quality=False,
                    confidence_penalty=1.0,
                    reference_days_count=n_ref,
                    detection_days_count=n_det,
                    rejection_reason=f"Insufficient history: {n_ref}/21 ref days, {n_det}/7 det days",
                )
                continue

            # Full quality check
            is_full = (n_ref >= self.config.min_reference_dates) and (n_det >= self.config.min_detection_dates)
            if is_full:
                penalty = 0.0
            else:
                ref_ratio = min(1.0, n_ref / self.config.min_reference_dates)
                det_ratio = min(1.0, n_det / self.config.min_detection_dates)
                penalty = 1.0 - (0.5 * ref_ratio + 0.5 * det_ratio)

            assessments[gw] = QualityAssessment(
                gateway_id=gw,
                is_eligible=True,
                is_full_quality=is_full,
                confidence_penalty=penalty,
                reference_days_count=n_ref,
                detection_days_count=n_det,
            )

        return assessments
