"""Operations-facing explanation generator for gateway diagnostics.

Produces deterministic, human-readable explanations (<= 300 chars) tailored
for operations managers and field technicians across all gateway statuses:
- Ranked in Top 15
- Eligible but unranked
- Ineligible due to decommissioning, future installation, or insufficient history
"""

from __future__ import annotations

import datetime as dt
from typing import Optional

from app.config import AppConfig
from app.domain.models import GatewayMaster, QualityAssessment, ScoredGateway

METRIC_DISPLAY_NAMES = {
    "offline_duration_sec": "offline duration",
    "disconnection_cnt": "disconnections",
    "reboot_cnt": "reboots",
}


class ExplanationBuilder:
    """Generates concise, informative reason strings compliant with length limits."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def _truncate(self, text: str) -> str:
        """Enforce strict max_reason_chars limit."""
        if len(text) > self.config.max_reason_chars:
            return text[: self.config.max_reason_chars - 3].rstrip() + "..."
        return text

    def build_ranked_reason(self, gateway: ScoredGateway, rank: int) -> str:
        """Construct operational reason for a top-15 ranked gateway."""
        tf = gateway.telemetry_features
        mf = gateway.meter_features
        qa = gateway.quality_assessment

        parts = []

        if tf.flagged_hours >= 10 or gateway.final_score >= 40.0:
            header = f"High priority (Rank {rank}):"
        elif tf.flagged_hours > 0 or gateway.final_score >= 15.0:
            header = f"Medium priority (Rank {rank}):"
        else:
            header = f"Capacity fill (Rank {rank}):"
        parts.append(header)

        if tf.flagged_hours > 0:
            metric_label = METRIC_DISPLAY_NAMES.get(tf.worst_metric, "telemetry anomalies")
            parts.append(
                f"{tf.flagged_hours} abnormal {metric_label} hour(s) in last 7 days vs 21-day baseline."
            )
        else:
            parts.append("Stable telemetry; dispatched on meter exposure / preventive backlog.")

        if mf.has_meter_data and mf.meters_expected > 0:
            pct = int(round(mf.read_success_ratio * 100))
            if pct < 90:
                parts.append(
                    f"Meter reads fell to {pct}% across {mf.exposure_meters} expected meters."
                )
            else:
                parts.append(f"Meter reads at {pct}% across {mf.exposure_meters} expected meters.")
        elif mf.exposure_meters > 0:
            parts.append(f"Serving {mf.exposure_meters} installed meters.")

        if not qa.is_full_quality:
            parts.append(f"[Degraded coverage: {qa.reference_days_count}/21 ref days].")

        return self._truncate(" ".join(parts))

    def build_unranked_reason(self, gateway: ScoredGateway, overall_rank: int) -> str:
        """Construct reason for an eligible gateway outside the top 15."""
        tf = gateway.telemetry_features
        mf = gateway.meter_features

        parts = [
            f"Eligible (Rank {overall_rank}, Score {gateway.final_score:.2f}) below weekly quota limit ({self.config.visit_limit})."
        ]

        if tf.flagged_hours > 0:
            metric_label = METRIC_DISPLAY_NAMES.get(tf.worst_metric, "telemetry anomalies")
            parts.append(f"Observed {tf.flagged_hours} abnormal {metric_label} hour(s).")
        else:
            parts.append("Telemetry stable with zero abnormal hours.")

        if mf.has_meter_data and mf.meters_expected > 0:
            pct = int(round(mf.read_success_ratio * 100))
            parts.append(f"Meter read success at {pct}%.")

        return self._truncate(" ".join(parts))

    def build_ineligible_reason(
        self,
        master: GatewayMaster,
        cutoff_date: dt.date,
        assessment: Optional[QualityAssessment] = None,
    ) -> str:
        """Construct explanation for an ineligible gateway."""
        if master.installed_on >= cutoff_date:
            return self._truncate(
                f"Ineligible: Gateway installed on {master.installed_on}, after target date {cutoff_date}."
            )
        if master.decommissioned_on and master.decommissioned_on < cutoff_date:
            return self._truncate(
                f"Ineligible: Gateway decommissioned on {master.decommissioned_on}, prior to target date {cutoff_date}."
            )
        if assessment and assessment.rejection_reason:
            return self._truncate(f"Ineligible: {assessment.rejection_reason}.")

        return self._truncate("Ineligible: Gateway failed operational readiness gates.")
