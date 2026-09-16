"""Integration test running the full 8-week prioritisation pipeline on synthetic data."""

from __future__ import annotations

import datetime as dt
import pathlib
import pandas as pd
import pytest

from app.config import AppConfig
from app.output.writer import ArtifactWriter
from app.services.ranking_service import RankingService
from validate_submission import validate


def test_full_pipeline_mock_data(test_config: AppConfig, tmp_path: pathlib.Path):
    out_csv = tmp_path / "predictions.csv"
    ranking_service = RankingService(test_config)
    writer = ArtifactWriter(test_config)

    weekly_ranks = {}
    for monday in test_config.scored_weeks:
        top_15 = ranking_service.get_top_ranked_gateways(monday, ranking_method="risk_v1")
        weekly_ranks[monday] = top_15

    df = writer.build_submission_frame(weekly_ranks)
    writer.write_csv_atomic(df, out_csv)

    assert out_csv.exists()
    assert len(df) == 120
    problems = validate(out_csv)
    assert len(problems) == 0, f"Validation errors: {problems}"
