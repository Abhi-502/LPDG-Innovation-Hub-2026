"""Full End-to-End API and Pipeline validation test."""

from __future__ import annotations

import pathlib
from fastapi.testclient import TestClient

from app.config import AppConfig
from main import run_pipeline_cli
from validate_submission import validate


def test_full_e2e_api_and_validation(test_client: TestClient, test_config: AppConfig, tmp_path: pathlib.Path):
    # 1. Trigger full 8-week prioritisation run via API
    response = test_client.post(
        "/api/v1/runs",
        json={"ranking_method": "risk_v1"},
    )
    assert response.status_code == 201
    run_info = response.json()
    run_id = run_info["run_id"]
    assert run_info["status"] == "SUCCEEDED"
    assert len(run_info["requested_weeks"]) == 8

    # 2. Check artifact output and validate with official challenge validator
    artifact_csv = pathlib.Path(run_info["artifact_paths"]["predictions_csv"])
    assert artifact_csv.exists()

    problems = validate(artifact_csv)
    assert not problems, f"Artifact validation failed: {problems}"

    # 3. Query predictions via API using run_id
    preds_res = test_client.get(f"/api/v1/weeks/2026-03-23/predictions?run_id={run_id}")
    assert preds_res.status_code == 200
    preds_data = preds_res.json()
    assert preds_data["count"] == 15
    top_gw = preds_data["predictions"][0]["gateway_id"]

    # 4. Query explainability endpoint for top gateway
    gw_res = test_client.get(f"/api/v1/weeks/2026-03-23/gateways/{top_gw}")
    assert gw_res.status_code == 200
    gw_data = gw_res.json()
    assert gw_data["status"] == "RANKED_TOP_15"
    assert gw_data["rank"] == 1
    assert len(gw_data["reason"]) <= 300

    # 5. Execute Part 1 CLI pipeline to verify boundary separation
    cli_out_path = tmp_path / "predictions_cli.csv"
    ret = run_pipeline_cli(
        data_dir=test_config.data_dir,
        out_path=cli_out_path,
        config=test_config,
    )
    assert ret == 0
    assert cli_out_path.exists()

    cli_problems = validate(cli_out_path)
    assert not cli_problems, f"CLI predictions validation failed: {cli_problems}"
