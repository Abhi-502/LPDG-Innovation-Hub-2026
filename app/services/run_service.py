"""Run management, OS locking, lifecycle states, and artifact isolation."""

from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import json
import logging
import os
import pathlib
import uuid
from typing import Dict, List, Optional
import pandas as pd

from app.config import AppConfig
from app.domain.errors import (
    ConcurrentRunError,
    RunNotFoundError,
    WeekNotSupportedError,
)
from app.domain.models import (
    PredictionItem,
    RunRecord,
    RunResponse,
    RunStatus,
    ScoredGateway,
)
from app.output.writer import ArtifactWriter
from app.services.ranking_service import RankingService

logger = logging.getLogger(__name__)


class RunService:
    """Manages execution runs, concurrency locking, and isolated run artifacts."""

    def __init__(
        self,
        config: AppConfig,
        ranking_service: RankingService,
        artifact_writer: Optional[ArtifactWriter] = None,
    ) -> None:
        self.config = config
        self.ranking_service = ranking_service
        self.artifact_writer = artifact_writer or ArtifactWriter(config)
        self._lock_file_obj = None

    @property
    def runs_dir(self) -> pathlib.Path:
        return self.config.artifacts_dir / "runs"

    @contextlib.contextmanager
    def acquire_execution_lock(self):
        """Acquire an exclusive OS-level file lock (non-blocking).

        Raises ConcurrentRunError (HTTP 409) if another execution holds the lock.
        """
        lock_path = self.config.run_lock_path
        lock_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            f = open(lock_path, "w+")
        except Exception as e:
            raise ConcurrentRunError(f"Unable to open lock file at {lock_path}: {e}") from e

        try:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, IOError, OSError):
            f.close()
            raise ConcurrentRunError("Another prioritisation run is currently in progress.")

        try:
            f.write(f"pid={os.getpid()}\ntimestamp={dt.datetime.now(dt.timezone.utc).isoformat()}\n")
            f.flush()
            yield
        finally:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            except Exception:
                pass
            f.close()

    def _generate_run_id(self) -> str:
        """Generate a human-readable unique run identifier."""
        ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
        rand = uuid.uuid4().hex[:6]
        return f"run_{ts}_{rand}"

    def get_run_dir(self, run_id: str) -> pathlib.Path:
        return self.runs_dir / run_id

    def save_metadata(self, run_id: str, metadata: dict) -> None:
        """Save run metadata to disk atomically."""
        run_dir = self.get_run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        meta_path = run_dir / "metadata.json"
        self.artifact_writer.write_json_atomic(metadata, meta_path)

    def load_metadata(self, run_id: str) -> Optional[dict]:
        """Load run metadata from disk, checking for orphaned state."""
        meta_path = self.get_run_dir(run_id) / "metadata.json"
        if not meta_path.exists():
            return None

        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None

        # Check for stale heartbeat / orphaned crash recovery
        if data.get("status") == RunStatus.RUNNING.value:
            heartbeat_str = data.get("heartbeat_at") or data.get("started_at")
            if heartbeat_str:
                try:
                    hb_time = dt.datetime.fromisoformat(heartbeat_str)
                    now_time = dt.datetime.now(dt.timezone.utc)
                    if (now_time - hb_time).total_seconds() > self.config.run_timeout_seconds:
                        data["status"] = RunStatus.ORPHANED.value
                        data["error_message"] = (
                            f"Run orphaned: Heartbeat exceeded timeout of {self.config.run_timeout_seconds}s."
                        )
                        self.save_metadata(run_id, data)
                except Exception:
                    pass

        return data

    def execute_run(
        self,
        requested_weeks: Optional[List[dt.date]] = None,
        ranking_method: Optional[str] = None,
    ) -> RunResponse:
        """Execute a prioritisation run synchronously with concurrency protection."""
        method = ranking_method or self.config.ranking_method
        target_weeks = requested_weeks or list(self.config.scored_weeks)
        run_id = self._generate_run_id()
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

        # 1. Acquire OS-level concurrency lock
        with self.acquire_execution_lock():
            # Initial state: CREATED -> RUNNING
            run_dir = self.get_run_dir(run_id)
            run_dir.mkdir(parents=True, exist_ok=True)

            meta: dict = {
                "run_id": run_id,
                "status": RunStatus.RUNNING.value,
                "ranking_method": method,
                "requested_weeks": [w.isoformat() for w in target_weeks],
                "started_at": now_iso,
                "heartbeat_at": now_iso,
                "completed_at": None,
                "error_message": None,
                "artifact_paths": {},
            }
            self.save_metadata(run_id, meta)

            try:
                weekly_ranks: Dict[dt.date, List[ScoredGateway]] = {}
                for monday in target_weeks:
                    # Update heartbeat per week
                    meta["heartbeat_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
                    self.save_metadata(run_id, meta)

                    top_15 = self.ranking_service.get_top_ranked_gateways(monday, ranking_method=method)
                    weekly_ranks[monday] = top_15

                # Build and write submission artifact under run directory
                submission_df = self.artifact_writer.build_submission_frame(weekly_ranks)
                csv_path = run_dir / "predictions.csv"
                self.artifact_writer.write_csv_atomic(submission_df, csv_path)

                # Finalize metadata
                meta["status"] = RunStatus.SUCCEEDED.value
                meta["completed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
                meta["artifact_paths"] = {
                    "predictions_csv": str(csv_path),
                    "metadata_json": str(run_dir / "metadata.json"),
                }
                self.save_metadata(run_id, meta)

            except Exception as e:
                logger.exception("Run %s failed with error: %s", run_id, e)
                meta["status"] = RunStatus.FAILED.value
                meta["completed_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
                meta["error_message"] = str(e)
                self.save_metadata(run_id, meta)
                raise

        return RunResponse(
            run_id=meta["run_id"],
            status=RunStatus(meta["status"]),
            ranking_method=meta["ranking_method"],
            requested_weeks=meta["requested_weeks"],
            started_at=meta["started_at"],
            heartbeat_at=meta.get("heartbeat_at"),
            completed_at=meta.get("completed_at"),
            error_message=meta.get("error_message"),
            artifact_paths=meta.get("artifact_paths", {}),
        )

    def get_run(self, run_id: str) -> RunResponse:
        """Fetch metadata for a specific run."""
        meta = self.load_metadata(run_id)
        if meta is None:
            raise RunNotFoundError(run_id)

        return RunResponse(
            run_id=meta["run_id"],
            status=RunStatus(meta["status"]),
            ranking_method=meta["ranking_method"],
            requested_weeks=meta["requested_weeks"],
            started_at=meta["started_at"],
            heartbeat_at=meta.get("heartbeat_at"),
            completed_at=meta.get("completed_at"),
            error_message=meta.get("error_message"),
            artifact_paths=meta.get("artifact_paths", {}),
        )

    def get_latest_successful_run(self, ranking_method: Optional[str] = None) -> Optional[RunResponse]:
        """Find latest successful run matching ranking_method."""
        if not self.runs_dir.exists():
            return None

        method = ranking_method or self.config.ranking_method
        all_runs = sorted(self.runs_dir.iterdir(), reverse=True)

        for r_path in all_runs:
            if not r_path.is_dir():
                continue
            meta = self.load_metadata(r_path.name)
            if meta and meta.get("status") == RunStatus.SUCCEEDED.value:
                if meta.get("ranking_method") == method:
                    return RunResponse(
                        run_id=meta["run_id"],
                        status=RunStatus(meta["status"]),
                        ranking_method=meta["ranking_method"],
                        requested_weeks=meta["requested_weeks"],
                        started_at=meta["started_at"],
                        heartbeat_at=meta.get("heartbeat_at"),
                        completed_at=meta.get("completed_at"),
                        error_message=meta.get("error_message"),
                        artifact_paths=meta.get("artifact_paths", {}),
                    )
        return None

    def get_predictions_for_week(
        self,
        week_start: dt.date,
        run_id: Optional[str] = None,
        ranking_method: Optional[str] = None,
    ) -> List[PredictionItem]:
        """Resolve predictions from an exact run, latest successful run, or fresh calculation."""
        self.ranking_service.validate_week(week_start)
        method = ranking_method or self.config.ranking_method

        target_run_id = run_id
        if target_run_id is None:
            latest = self.get_latest_successful_run(ranking_method=method)
            if latest:
                target_run_id = latest.run_id

        # If a run_id is specified or found, read from its predictions.csv
        if target_run_id:
            run_meta = self.get_run(target_run_id)
            if run_meta.status != RunStatus.SUCCEEDED:
                raise RunNotFoundError(f"Run '{target_run_id}' has status {run_meta.status}, not SUCCEEDED.")

            csv_path = self.get_run_dir(target_run_id) / "predictions.csv"
            if not csv_path.exists():
                raise RunNotFoundError(f"Predictions artifact missing for run '{target_run_id}'.")

            df = pd.read_csv(csv_path)
            week_str = week_start.isoformat()
            sub = df[df["week_start"] == week_str].sort_values("rank")
            if not sub.empty:
                items = []
                for _, row in sub.iterrows():
                    items.append(
                        PredictionItem(
                            rank=int(row["rank"]),
                            gateway_id=str(row["gateway_id"]),
                            score=float(row["score"]),
                            reason=str(row["reason"]),
                            ranking_method=run_meta.ranking_method,
                        )
                    )
                return items

        # Fallback: compute dynamically using ranking service
        return self.ranking_service.get_predictions_for_week(week_start, ranking_method=method)
