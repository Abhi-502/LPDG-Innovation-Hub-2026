#!/usr/bin/env python3
"""Main entry point for Gateway Visit Prioritisation (Part 1 CLI + Part 2 API).

Usage:
  1. CLI Pipeline Execution (Part 1 compliant):
     python main.py --data data --out predictions.csv

  2. API Server Execution (Part 2 FastAPI Service):
     python main.py --serve --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import pathlib
import sys
from typing import Dict, List

import uvicorn

from app.config import AppConfig, get_config
from app.domain.models import ScoredGateway
from app.output.writer import ArtifactWriter
from app.services.ranking_service import RankingService


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def run_pipeline_cli(data_dir: pathlib.Path, out_path: pathlib.Path, config: AppConfig) -> int:
    """Execute standard Part 1 deterministic prioritisation run."""
    logger = logging.getLogger("main.cli")
    logger.info("Starting deterministic gateway prioritisation pipeline")
    logger.info("Data directory: %s", data_dir)
    logger.info("Target output: %s", out_path)

    custom_config = AppConfig(
        data_dir=data_dir,
        artifacts_dir=out_path.parent / "artifacts",
        ranking_method=config.ranking_method,
    )

    ranking_service = RankingService(custom_config)
    writer = ArtifactWriter(custom_config)

    weekly_ranks: Dict[dt.date, List[ScoredGateway]] = {}
    for monday in custom_config.scored_weeks:
        logger.info("Scoring cutoff week: %s", monday)
        top_15 = ranking_service.get_top_ranked_gateways(monday, ranking_method=custom_config.ranking_method)
        weekly_ranks[monday] = top_15

    df = writer.build_submission_frame(weekly_ranks)
    writer.write_csv_atomic(df, out_path)
    logger.info("Pipeline completed successfully. Wrote %d rows to %s", len(df), out_path)
    return 0


def run_api_server(host: str, port: int, reload: bool = False) -> None:
    """Start FastAPI server with Uvicorn."""
    uvicorn.run("app.api.app:app", host=host, port=port, reload=reload)


def main(argv: list[str] | None = None) -> int:
    config = get_config()
    setup_logging(config.log_level)

    parser = argparse.ArgumentParser(
        description="Gateway Visit Prioritisation Engine (Part 1 CLI + Part 2 API)"
    )
    parser.add_argument(
        "--data",
        type=pathlib.Path,
        default=config.data_dir,
        help="Path to input data directory containing gateway_master.csv, telemetry, etc.",
    )
    parser.add_argument(
        "--out",
        type=pathlib.Path,
        default=pathlib.Path("predictions.csv"),
        help="Path for generated output CSV predictions file.",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="Start the FastAPI HTTP application server instead of running the CLI pipeline.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=config.api_host,
        help="HTTP host to bind when running API server.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=config.api_port,
        help="HTTP port to bind when running API server.",
    )

    args = parser.parse_args(argv)

    if args.serve:
        run_api_server(host=args.host, port=args.port)
        return 0

    return run_pipeline_cli(data_dir=args.data, out_path=args.out, config=config)


if __name__ == "__main__":
    sys.exit(main())
