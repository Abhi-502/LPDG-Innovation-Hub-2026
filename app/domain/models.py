"""Domain entities and data transfer schemas for the prioritisation engine."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RunStatus(str, Enum):
    """Lifecycle states of a prioritisation execution run."""
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ORPHANED = "ORPHANED"


class GatewayStatus(str, Enum):
    """Operational status of a gateway evaluation."""
    RANKED_TOP_15 = "RANKED_TOP_15"
    ELIGIBLE_UNRANKED = "ELIGIBLE_UNRANKED"
    INELIGIBLE = "INELIGIBLE"


@dataclass(frozen=True)
class GatewayMaster:
    """Master record for a physical gateway."""
    gateway_id: str
    tenant: str
    site_type: str
    region: str
    hw_model: str
    installed_on: dt.date
    decommissioned_on: Optional[dt.date]
    n_meters_installed: int


@dataclass(frozen=True)
class QualityAssessment:
    """Assessment of gateway data quality and history sufficiency."""
    gateway_id: str
    is_eligible: bool
    is_full_quality: bool
    confidence_penalty: float  # 0.0 (no penalty) to 1.0 (full penalty)
    reference_days_count: int
    detection_days_count: int
    rejection_reason: Optional[str] = None


@dataclass(frozen=True)
class TelemetryFeatures:
    """Computed telemetry features for a single gateway."""
    gateway_id: str
    flagged_hours: int
    total_detection_hours: int
    persistence_ratio: float  # 0.0 to 1.0
    avg_anomaly_severity: float  # Mean robust z-score across flagged hours
    max_anomaly_severity: float  # Max robust z-score capped
    recency_score: float  # 0.0 to 1.0
    worst_metric: str
    total_recent_offline_sec: float
    importance_multiplier: float = 1.0


@dataclass(frozen=True)
class MeterImpactFeatures:
    """Computed meter-read impact features for a single gateway."""
    gateway_id: str
    meters_expected: int
    meters_read: int
    read_success_ratio: float  # 0.0 to 1.0
    degradation_vs_history: float  # Drop in read success ratio vs baseline
    exposure_meters: int  # Max of meters_expected and n_meters_installed
    has_meter_data: bool


@dataclass(frozen=True)
class ScoredGateway:
    """Complete score breakdown and operational attributes for ranking."""
    gateway_id: str
    final_score: float  # 0.0 to 100.0
    telemetry_risk: float  # 0.0 to 100.0
    meter_impact: float  # 0.0 to 100.0
    data_confidence: float  # 0.0 to 100.0
    telemetry_features: TelemetryFeatures
    meter_features: MeterImpactFeatures
    quality_assessment: QualityAssessment


@dataclass(frozen=True)
class RunRecord:
    """Historical execution run record."""
    run_id: str
    status: RunStatus
    ranking_method: str
    requested_weeks: List[str]
    started_at: str
    heartbeat_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    artifact_paths: Dict[str, str] = field(default_factory=dict)


# --- API Pydantic Models ---

class PredictionItem(BaseModel):
    """A single ranked gateway recommendation."""
    rank: int = Field(..., ge=1, le=15, description="Weekly priority rank from 1 to 15")
    gateway_id: str = Field(..., description="12-character hex gateway identifier")
    score: float = Field(..., ge=0.0, le=100.0, description="Composite prioritisation score (0-100)")
    reason: str = Field(..., max_length=300, description="Operations-ready explanation string")
    ranking_method: str = Field(..., description="Ranking algorithm strategy used")


class WeeklyPredictionsResponse(BaseModel):
    """Response payload for weekly predictions."""
    week_start: str = Field(..., description="Target Monday date in YYYY-MM-DD format")
    ranking_method: str = Field(..., description="Algorithm used to compute predictions")
    run_id: Optional[str] = Field(None, description="Run ID producing these artifacts")
    count: int = Field(..., description="Number of gateways ranked (always 15)")
    predictions: List[PredictionItem] = Field(..., description="List of 15 ranked gateways")


class GatewayEvaluationResponse(BaseModel):
    """Detailed explanation and evaluation for a specific gateway."""
    gateway_id: str
    week_start: str
    status: GatewayStatus
    rank: Optional[int] = None
    score: Optional[float] = None
    ranking_method: str
    reason: str
    is_eligible: bool
    details: Dict[str, Any] = Field(default_factory=dict)


class CreateRunRequest(BaseModel):
    """Request payload for triggering an execution run."""
    weeks: Optional[List[str]] = Field(
        None,
        description="Optional list of Monday dates (YYYY-MM-DD). If omitted, processes all 8 scored weeks.",
    )
    ranking_method: Optional[str] = Field(
        None,
        description="Optional ranking algorithm strategy ('risk_v1' or 'baseline'). Defaults to system config.",
    )


class RunResponse(BaseModel):
    """Response model for run metadata and execution status."""
    run_id: str
    status: RunStatus
    ranking_method: str
    requested_weeks: List[str]
    started_at: str
    heartbeat_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    artifact_paths: Dict[str, str] = Field(default_factory=dict)


class HealthResponse(BaseModel):
    """System health and readiness status."""
    status: str = Field(..., json_schema_extra={"example": "healthy"})
    timestamp: str
    version: str
    environment: str
    data_dir_ready: bool
    ranking_method: str
