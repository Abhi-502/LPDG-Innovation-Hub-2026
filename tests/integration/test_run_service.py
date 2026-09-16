"""Integration tests for RunService and lifecycle execution."""

from __future__ import annotations

import datetime as dt
import pytest

from app.config import AppConfig
from app.domain.models import RunStatus
from app.services.ranking_service import RankingService
from app.services.run_service import RunService
from validate_submission import validate


def test_run_service_execution_creates_isolated_artifacts(test_config: AppConfig):
    ranking_service = RankingService(test_config)
    run_service = RunService(test_config, ranking_service)

    # Execute run for 2 weeks
    target_weeks = [dt.date(2026, 3, 16), dt.date(2026, 3, 23)]
    run_resp = run_service.execute_run(requested_weeks=target_weeks)

    assert run_resp.status == RunStatus.SUCCEEDED
    assert run_resp.run_id.startswith("run_")
    assert run_resp.completed_at is not None

    # Check artifacts exist
    run_dir = run_service.get_run_dir(run_resp.run_id)
    csv_path = run_dir / "predictions.csv"
    meta_path = run_dir / "metadata.json"

    assert csv_path.exists()
    assert meta_path.exists()

    # Get predictions through run_service
    preds = run_service.get_predictions_for_week(
        week_start=dt.date(2026, 3, 23),
        run_id=run_resp.run_id,
    )
    assert len(preds) == 15
    assert preds[0].ranking_method == test_config.ranking_method
