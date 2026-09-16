"""Submission file formatting, internal schema verification, and atomic I/O.

Ensures strict compliance with the competition schema and writes files atomically.
API executions persist artifacts under artifacts/runs/<run_id>/ without modifying root predictions.csv.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import os
import pathlib
import tempfile
from typing import Dict, List, Optional
import pandas as pd

from app.config import AppConfig
from app.domain.models import ScoredGateway
from app.explanations.builder import ExplanationBuilder
from app.repositories.gateways import normalise_gateway_id

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["week_start", "rank", "gateway_id", "score", "reason"]


class ArtifactWriter:
    """Formats and writes run artifacts atomically."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.explanation_builder = ExplanationBuilder(config)

    def build_submission_frame(
        self, weekly_ranks: Dict[dt.date, List[ScoredGateway]]
    ) -> pd.DataFrame:
        """Convert weekly ranked gateways into a validated submission DataFrame."""
        rows = []
        for monday, gateways in weekly_ranks.items():
            if len(gateways) != self.config.visit_limit:
                raise ValueError(
                    f"Week {monday}: Expected {self.config.visit_limit} gateways, found {len(gateways)}"
                )

            for rank_idx, gw in enumerate(gateways, start=1):
                reason_text = self.explanation_builder.build_ranked_reason(gw, rank_idx)
                rows.append(
                    {
                        "week_start": monday.isoformat(),
                        "rank": rank_idx,
                        "gateway_id": gw.gateway_id,
                        "score": round(float(gw.final_score), 4),
                        "reason": reason_text,
                    }
                )

        df = pd.DataFrame(rows, columns=REQUIRED_COLUMNS)
        self.validate_internal(df, expected_weeks=list(weekly_ranks.keys()))
        return df

    def validate_internal(
        self, df: pd.DataFrame, expected_weeks: Optional[List[dt.date]] = None
    ) -> None:
        """Verify strict schema, row counts, ranges, and reasons internally."""
        if list(df.columns) != REQUIRED_COLUMNS:
            raise ValueError(f"Invalid columns: expected {REQUIRED_COLUMNS}, got {list(df.columns)}")

        target_weeks = expected_weeks or list(self.config.scored_weeks)
        expected_rows = len(target_weeks) * self.config.visit_limit
        if len(df) != expected_rows:
            raise ValueError(f"Expected {expected_rows} rows, got {len(df)}")

        weeks = pd.to_datetime(df["week_start"]).dt.date
        if sorted(weeks.unique()) != sorted(target_weeks):
            raise ValueError(f"Scored weeks mismatch: {sorted(weeks.unique())} vs {sorted(target_weeks)}")

        bad_ids = [v for v in df["gateway_id"] if normalise_gateway_id(v) is None]
        if bad_ids:
            raise ValueError(f"Found invalid gateway IDs: {bad_ids[:5]}")

        if not pd.api.types.is_numeric_dtype(df["score"]) or df["score"].isna().any():
            raise ValueError("Score column must be numeric and non-null")

        reasons = df["reason"].astype(str).str.strip()
        if (reasons == "").any() or df["reason"].isna().any():
            raise ValueError("Found empty or NaN reasons")
        if (reasons.str.len() > self.config.max_reason_chars).any():
            raise ValueError(f"Reasons exceed max char limit ({self.config.max_reason_chars})")

        for week, part in df.groupby(weeks):
            if len(part) != self.config.visit_limit:
                raise ValueError(f"Week {week} has {len(part)} rows, expected {self.config.visit_limit}")
            ranks = list(part["rank"])
            if ranks != list(range(1, self.config.visit_limit + 1)):
                raise ValueError(f"Week {week} ranks invalid: {ranks}")
            if part["gateway_id"].nunique() != self.config.visit_limit:
                raise ValueError(f"Week {week} contains duplicate gateway IDs")

    def write_csv_atomic(self, df: pd.DataFrame, out_path: pathlib.Path) -> None:
        """Write DataFrame to target path atomically via a temporary file."""
        out_path = out_path.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=out_path.parent,
            prefix=f".{out_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp:
            tmp_path = pathlib.Path(tmp.name)
            df.to_csv(tmp_path, index=False)

        os.replace(tmp_path, out_path)
        logger.info("Successfully wrote %d rows atomically to %s", len(df), out_path)

    def write_json_atomic(self, data: dict, out_path: pathlib.Path) -> None:
        """Write JSON dict to target path atomically."""
        out_path = out_path.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            dir=out_path.parent,
            prefix=f".{out_path.name}.",
            suffix=".tmp",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp_path = pathlib.Path(tmp.name)
            json.dump(data, tmp, indent=2)

        os.replace(tmp_path, out_path)
        logger.info("Successfully wrote JSON metadata atomically to %s", out_path)
