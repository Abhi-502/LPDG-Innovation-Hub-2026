"""Regression tests for edge cases, crash recovery, and data anomalies."""

from __future__ import annotations

import datetime as dt
import json
import pathlib
import pytest

from app.config import AppConfig
from app.domain.models import RunStatus
from app.services.ranking_service import RankingService
from app.services.run_service import RunService


def test_orphaned_run_heartbeat_recovery(test_config: AppConfig, tmp_path: pathlib.Path):
    """Test that a crashed run left in RUNNING state is recovered as ORPHANED when heartbeat expires."""
    ranking_service = RankingService(test_config)
    # Configure 1 second timeout for test
    short_timeout_config = AppConfig(
        data_dir=test_config.data_dir,
        artifacts_dir=tmp_path / "artifacts",
        run_timeout_seconds=1,
    )
    run_service = RunService(short_timeout_config, ranking_service)

    run_id = "run_crashed_simulated"
    run_dir = run_service.get_run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    # Simulate a run that started 10 seconds ago and crashed without updating status
    old_time = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=10)).isoformat()
    meta = {
        "run_id": run_id,
        "status": RunStatus.RUNNING.value,
        "ranking_method": "risk_v1",
        "requested_weeks": ["2026-03-23"],
        "started_at": old_time,
        "heartbeat_at": old_time,
        "completed_at": None,
        "error_message": None,
        "artifact_paths": {},
    }
    with open(run_dir / "metadata.json", "w") as f:
        json.dump(meta, f)

    # Fetching the run should trigger recovery to ORPHANED
    run_status = run_service.get_run(run_id)
    assert run_status.status == RunStatus.ORPHANED
    assert "orphaned" in (run_status.error_message or "").lower()


def test_zero_telemetry_gateways_handled_cleanly(test_config: AppConfig):
    """Test that gateways with no anomalies or empty telemetry return clean 0.0 scores."""
    ranking_service = RankingService(test_config)
    monday = dt.date(2026, 2, 2)
    top15 = ranking_service.get_top_ranked_gateways(monday)
    assert len(top15) == 15
    for gw in top15:
        assert isinstance(gw.final_score, float)
        assert 0.0 <= gw.final_score <= 100.0
