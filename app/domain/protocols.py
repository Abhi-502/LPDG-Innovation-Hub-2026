"""Domain interfaces and protocols."""

from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional, Protocol, runtime_checkable
import pandas as pd

from app.domain.models import (
    GatewayMaster,
    MeterImpactFeatures,
    QualityAssessment,
    ScoredGateway,
    TelemetryFeatures,
)


@runtime_checkable
class RankingStrategy(Protocol):
    """Protocol for pluggable gateway prioritisation algorithms."""

    @property
    def name(self) -> str:
        """Unique strategy name identifier (e.g. 'risk_v1', 'baseline')."""
        ...

    def score_gateways(
        self,
        telemetry_feats: Dict[str, TelemetryFeatures],
        meter_feats: Dict[str, MeterImpactFeatures],
        assessments: Dict[str, QualityAssessment],
    ) -> List[ScoredGateway]:
        """Compute scores across all eligible gateways."""
        ...

    def rank_gateways(
        self,
        scored_gateways: List[ScoredGateway],
        visit_limit: int = 15,
    ) -> List[ScoredGateway]:
        """Sort and select top candidate gateways deterministically."""
        ...

    def score_single(
        self,
        tf: TelemetryFeatures,
        mf: MeterImpactFeatures,
        qa: QualityAssessment,
    ) -> float:
        """Calculate single gateway final score."""
        ...


@runtime_checkable
class GatewayRepositoryProtocol(Protocol):
    """Protocol for gateway master data access."""

    def load_master(self) -> pd.DataFrame:
        ...

    def get_gateway(self, gateway_id: str) -> Optional[GatewayMaster]:
        ...

    def exists(self, gateway_id: str) -> bool:
        ...


@runtime_checkable
class TelemetryRepositoryProtocol(Protocol):
    """Protocol for telemetry time-series storage access."""

    def load_telemetry(
        self,
        cutoff_utc: pd.Timestamp,
        trailing_days: int,
    ) -> pd.DataFrame:
        ...


@runtime_checkable
class MeterReadRepositoryProtocol(Protocol):
    """Protocol for meter read history access."""

    def load_meter_reads(
        self,
        cutoff_date: dt.date,
        lookback_weeks: int = 4,
    ) -> pd.DataFrame:
        ...
