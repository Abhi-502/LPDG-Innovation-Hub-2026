"""Unit tests for OS-level concurrency locking."""

from __future__ import annotations

import fcntl
import pytest

from app.config import AppConfig
from app.domain.errors import ConcurrentRunError
from app.services.ranking_service import RankingService
from app.services.run_service import RunService


def test_concurrency_lock_prevents_overlapping_runs(test_config: AppConfig):
    ranking_service = RankingService(test_config)
    run_service = RunService(test_config, ranking_service)

    # 1. Acquire the lock explicitly in context
    with run_service.acquire_execution_lock():
        # 2. Attempting to acquire a second lock must raise ConcurrentRunError
        with pytest.raises(ConcurrentRunError):
            with run_service.acquire_execution_lock():
                pass

    # 3. After exit, lock should be free and acquirable again
    with run_service.acquire_execution_lock():
        assert True
