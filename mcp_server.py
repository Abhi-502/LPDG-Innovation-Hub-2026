#!/usr/bin/env python3
"""Model Context Protocol (MCP) Server for Gateway Visit Prioritisation.

Exposes the prioritisation engine, gateway inspection tools, and validation
as standard MCP tools over stdio for AI assistants and IDE integrations.
"""

from __future__ import annotations

import datetime as dt
import json
import logging
import pathlib
import sys
from typing import Any, Dict, List, Optional

import pandas as pd

from app.config import AppConfig, get_config
from app.domain.models import ScoredGateway
from app.output.writer import ArtifactWriter
from app.repositories.gateways import normalise_gateway_id
from app.services.gateway_service import GatewayService
from app.services.ranking_service import RankingService
from validate_submission import validate


def handle_prioritise_visits(arguments: Dict[str, Any]) -> str:
    data_dir_str = arguments.get("data_dir")
    out_path_str = arguments.get("out_path", "predictions.csv")

    config = get_config()
    data_dir = pathlib.Path(data_dir_str) if data_dir_str else config.data_dir
    out_path = pathlib.Path(out_path_str)

    if not data_dir.exists():
        fallback = pathlib.Path("/Users/macbook/Downloads/Innovation Hub 2026/data")
        if fallback.exists():
            data_dir = fallback

    app_config = AppConfig(
        data_dir=data_dir,
        artifacts_dir=out_path.parent / "artifacts",
        ranking_method=config.ranking_method,
    )

    ranking_service = RankingService(app_config)
    writer = ArtifactWriter(app_config)

    weekly_ranks: Dict[dt.date, List[ScoredGateway]] = {}
    for monday in app_config.scored_weeks:
        top_15 = ranking_service.get_top_ranked_gateways(monday, ranking_method=app_config.ranking_method)
        weekly_ranks[monday] = top_15

    df = writer.build_submission_frame(weekly_ranks)
    writer.write_csv_atomic(df, out_path)
    problems = validate(out_path)

    summary = {
        "status": "SUCCESS" if not problems else "VALIDATION_FAILED",
        "total_rows": len(df),
        "weeks_scored": df["week_start"].nunique(),
        "out_file": str(out_path.resolve()),
        "validation_problems": problems,
        "sample_top_3": df.head(3).to_dict(orient="records"),
    }
    return json.dumps(summary, indent=2)


def handle_inspect_gateway(arguments: Dict[str, Any]) -> str:
    data_dir_str = arguments.get("data_dir")
    config = get_config()
    data_dir = pathlib.Path(data_dir_str) if data_dir_str else config.data_dir

    if not data_dir.exists():
        fallback = pathlib.Path("/Users/macbook/Downloads/Innovation Hub 2026/data")
        if fallback.exists():
            data_dir = fallback

    gateway_id_raw = arguments.get("gateway_id")
    gw = normalise_gateway_id(gateway_id_raw)
    if not gw:
        return json.dumps({"error": f"Invalid gateway ID: {gateway_id_raw}"})

    week_str = arguments.get("week_date", "2026-02-02")
    try:
        monday = dt.date.fromisoformat(week_str)
    except Exception as e:
        return json.dumps({"error": f"Invalid date format: {week_str}, expected YYYY-MM-DD"})

    app_config = AppConfig(data_dir=data_dir)
    ranking_service = RankingService(app_config)
    gateway_service = GatewayService(app_config, ranking_service=ranking_service)

    try:
        res = gateway_service.evaluate_gateway(monday, gw)
        result = {
            "gateway_id": res.gateway_id,
            "week_start": str(res.week_start),
            "status": res.status.value,
            "rank": res.rank,
            "score": res.score,
            "reason": res.reason,
            "is_eligible": res.is_eligible,
            "details": res.details,
        }
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def handle_validate_predictions(arguments: Dict[str, Any]) -> str:
    path = pathlib.Path(arguments.get("predictions_path", "predictions.csv"))
    if not path.exists():
        return json.dumps({"error": f"File not found: {path}"})

    problems = validate(path)
    return json.dumps(
        {
            "path": str(path.resolve()),
            "is_valid": len(problems) == 0,
            "problems": problems,
        },
        indent=2,
    )


TOOLS = [
    {
        "name": "prioritise_visits",
        "description": "Runs the full 8-week deterministic gateway visit prioritisation pipeline and writes predictions.csv.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data_dir": {"type": "string", "description": "Path to data directory"},
                "out_path": {"type": "string", "description": "Path to output predictions.csv"},
            },
        },
    },
    {
        "name": "inspect_gateway",
        "description": "Inspects telemetry health, coverage, and master record status for a specific gateway on a given week.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "gateway_id": {"type": "string", "description": "12-hex gateway ID or colon format"},
                "week_date": {"type": "string", "description": "Target Monday in YYYY-MM-DD format (default: 2026-02-02)"},
                "data_dir": {"type": "string", "description": "Path to data directory"},
            },
            "required": ["gateway_id"],
        },
    },
    {
        "name": "validate_predictions",
        "description": "Runs the official Innovation Hub validator against a predictions.csv file.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "predictions_path": {"type": "string", "description": "Path to predictions.csv file"},
            },
            "required": ["predictions_path"],
        },
    },
]


def main():
    """Simple JSON-RPC / MCP stdio server loop."""
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
            req_id = req.get("id")
            method = req.get("method")

            if method == "tools/list":
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
            elif method == "tools/call":
                params = req.get("params", {})
                name = params.get("name")
                args = params.get("arguments", {})

                if name == "prioritise_visits":
                    content = handle_prioritise_visits(args)
                elif name == "inspect_gateway":
                    content = handle_inspect_gateway(args)
                elif name == "validate_predictions":
                    content = handle_validate_predictions(args)
                else:
                    content = json.dumps({"error": f"Unknown tool: {name}"})

                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"content": [{"type": "text", "text": content}]},
                }
            elif method == "initialize":
                resp = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "serverInfo": {"name": "gateway-prioritisation-mcp", "version": "1.0.0"},
                        "capabilities": {"tools": {}},
                    },
                }
            else:
                resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}

            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
        except Exception as e:
            err_resp = {
                "jsonrpc": "2.0",
                "id": req.get("id") if "req" in locals() else None,
                "error": {"code": -32603, "message": str(e)},
            }
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
