"""Global test fixtures and configurations."""

from __future__ import annotations

import pathlib
from typing import Generator
import pytest
from fastapi.testclient import TestClient

from app.api.app import create_app
from app.config import AppConfig, get_config
from tests.fixtures.data_generator import generate_mock_environment


@pytest.fixture(scope="session")
def global_mock_data_dir(tmp_path_factory) -> pathlib.Path:
    """Create a persistent synthetic dataset for testing."""
    base_dir = tmp_path_factory.mktemp("test_workspace")
    data_dir = base_dir / "data"
    generate_mock_environment(data_dir=data_dir, num_gateways=25)
    return base_dir


@pytest.fixture
def test_config(global_mock_data_dir: pathlib.Path, tmp_path: pathlib.Path) -> AppConfig:
    """Return an AppConfig pointing to the test data directory and an isolated artifacts folder."""
    data_dir = global_mock_data_dir / "data"
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    return AppConfig(
        app_env="test",
        data_dir=data_dir,
        artifacts_dir=artifacts_dir,
        run_lock_path=artifacts_dir / ".run.lock",
        ranking_method="risk_v1",
        visit_limit=15,
        run_timeout_seconds=300,
    )


@pytest.fixture
def test_client(test_config: AppConfig) -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient configured for the test environment."""
    app = create_app(test_config)
    app.dependency_overrides[get_config] = lambda: test_config
    with TestClient(app) as client:
        yield client
