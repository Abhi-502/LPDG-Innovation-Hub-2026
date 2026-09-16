# Gateway Visit Prioritisation System (Unified Part 1 & Part 2)

> **LPDG Innovation Hub Selection Challenge 2026 — Deterministic Prioritisation Engine & Production Software Development API**

---

## 1. Executive Summary

This repository presents the unified, production-grade **Gateway Visit Prioritisation System**, seamlessly combining the deterministic, point-in-time decision engine of **Part 1** with the modular clean architecture, REST API, OS-level concurrency control, and developer tooling of **Part 2 (Software Development)**.

### Core System Highlights
- **100% Submission Compliant (Part 1)**: Generates the official `predictions.csv` with exactly 15 unique gateways for each of the 8 evaluation weeks (120 rows total), full $\le 300$-character explanations, and 0 validation errors on `validate_submission.py`.
- **Deterministic & Point-in-Time**: Evaluates each Monday cutoff using *only* data available strictly before Monday 00:00:00 UTC (`[start, cutoff)` half-open interval), eliminating lookahead leakage.
- **Strict Window Isolation**: Decouples the 21-day historical reference baseline `[cutoff - 28d, cutoff - 7d)` from the 7-day detection window `[cutoff - 7d, cutoff)`. Prolonged failures cannot self-contaminate baseline statistics.
- **Robust Multi-Signal Scoring**: Non-parametric robust statistics (Median / MAD with physical scale floors) combined with downstream meter-read failure degradation and sublinear fleet exposure scaling ($\ln(1 + \text{meters})$).
- **Clean Layered Architecture (Part 2)**: Modular separation across API, Service, Strategy, Domain, and Repository layers.
- **Pluggable Strategy Pattern**: Runtime algorithm switching via `RankingStrategy` protocol (`risk_v1`, `baseline`).
- **OS-Level Concurrency Control**: Single-run serialized execution via atomic file locks (`fcntl.flock`) returning `409 Conflict` on overlapping runs with stale heartbeat crash recovery.
- **Multiple Developer Interfaces**: CLI pipeline, FastAPI REST API with OpenAPI/Swagger (`/docs`), and Model Context Protocol (MCP) server.

---

## 2. System Architecture

```
                                  ┌───────────────────────────┐
                                  │   Data Sources (data/)    │
                                  │ telemetry/, master, meter │
                                  └─────────────┬─────────────┘
                                                │
                                                ▼
                                  ┌───────────────────────────┐
                                  │    Repositories (data/)   │
                                  │ Telemetry, Gateway, Meter │
                                  └─────────────┬─────────────┘
                                                │
                                                ▼
                                  ┌───────────────────────────┐
                                  │  FeatureBuilder (Median)  │
                                  │  21d Ref vs 7d Det (MAD)  │
                                  └─────────────┬─────────────┘
                                                │
                        ┌───────────────────────┴───────────────────────┐
                        ▼                                               ▼
         ┌─────────────────────────────┐                 ┌─────────────────────────────┐
         │  RankingStrategy Protocol   │                 │     OS Run Lock (fcntl)     │
         │ - RiskRanker (risk_v1)      │                 │  Run State Machine +        │
         │ - Baseline3SigmaRanker      │                 │  Artifact Isolation Writer  │
         └──────────────┬──────────────┘                 └──────────────┬──────────────┘
                        │                                               │
                        └───────────────────────┬───────────────────────┘
                                                ▼
                                  ┌───────────────────────────┐
                                  │      Service Layer        │
                                  │ Ranking, Gateway, Run Svc │
                                  └─────────────┬─────────────┘
                                                │
                   ┌────────────────────────────┼────────────────────────────┐
                   ▼                            ▼                            ▼
         ┌───────────────────┐        ┌───────────────────┐        ┌───────────────────┐
         │   Part 1 CLI      │        │   FastAPI REST    │        │    MCP Server     │
         │ (predictions.csv) │        │ (/health, /weeks) │        │   (JSON-RPC / AI) │
         └───────────────────┘        └───────────────────┘        └───────────────────┘
```

---

## 3. Quick Start

### 3.1 Setup Environment
```bash
# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
```

### 3.2 Part 1: Execute CLI Pipeline (One Command)
Produces the official `predictions.csv`:
```bash
# Standard run (reads ./data and generates ./predictions.csv)
make run
# or:
python main.py --data data --out predictions.csv
```

### 3.3 Validate Submission
Runs the official Innovation Hub validator:
```bash
make validate
# or:
python validate_submission.py predictions.csv
```

### 3.4 Part 2: Start FastAPI REST API Server
```bash
make api
# or:
python main.py --serve --host 0.0.0.0 --port 8000
```
- **Interactive Swagger UI**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`
- **OpenAPI Schema**: `http://localhost:8000/openapi.json`

### 3.5 Run Model Context Protocol (MCP) Server
```bash
python mcp_server.py
```

### 3.6 Run Automated Tests
```bash
make test
# or:
pytest -v
```

### 3.7 Run with Docker & Docker Compose
```bash
# Docker build & run
make docker-build
make docker-run

# Or via Docker Compose
docker compose up --build
```

---

## 4. Scoring & Ranking Formulation

All score components are normalized to an explicit **0 to 100** composite scale:

$$\text{Final Score} = 0.70 \times \text{Telemetry Risk} + 0.25 \times \text{Meter Impact} + 0.05 \times \text{Data Confidence}$$

1. **Telemetry Risk ($0 - 100$)**:
   $$\text{Telemetry Risk} = (0.45 \times \text{Persistence} + 0.35 \times \text{Severity} + 0.20 \times \text{Recency}) \times \text{Importance Multiplier}$$
   - *Persistence*: Fraction of anomalous hours ($z > 3.0$) in the 7-day detection window.
   - *Severity*: Mean robust z-score $\left(\frac{x - \text{Median}}{\text{MAD} \times 1.4826}\right)$ capped at $10.0\sigma$.
   - *Recency*: Exponential time-decay weighting favoring failures occurring in the final 48 hours.
   - *Scale Floors*: Physical minimum scale floors (e.g. 60.0s for offline duration, 1.0 for counts) prevent zero-MAD false alarms.

2. **Meter Impact ($0 - 100$)**:
   $$\text{Meter Impact} = \left(0.60 \times (1 - \text{Read Success}) + 0.40 \times \text{Degradation}\right) \times \min\left(1.0, \frac{\ln(1 + \text{Meters})}{\ln(1 + 500)}\right) \times 100$$
   - Sublinear logarithmic scaling accounts for customer impact without allowing mega-sites to permanently starve smaller sites.

3. **Data Confidence ($0 - 100$)**:
   - $100$ for full 21-day reference and 7-day detection coverage; proportionally discounted when coverage is degraded.

4. **Deterministic 4-Key Tie Breaking**:
   `(-final_score, -exposure_meters, -total_recent_offline_sec, gateway_id)` ensures 100% reproducible ordering regardless of environment or row order.

---

## 5. API Endpoints Overview

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | System health check and dataset readiness verification |
| `GET` | `/api/v1/weeks/{week_start}/predictions` | Retrieve top 15 ranked gateways for a given Monday cutoff |
| `GET` | `/api/v1/gateways/{gateway_id}/explanation` | Detailed diagnostic explanation for ranked, unranked, or ineligible gateways |
| `POST`| `/api/v1/runs` | Trigger a new prioritisation execution run with concurrency locking |
| `GET` | `/api/v1/runs/{run_id}` | Retrieve execution run status, metadata, and artifact paths |

For complete request/response schemas and curl examples, see [docs/API.md](file:///Users/macbook/Desktop/CHALLENGE/docs/API.md).

---

## 6. Configuration & Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `APP_ENV` | `development` | Deployment environment (`development`, `production`, `test`) |
| `API_HOST` | `0.0.0.0` | Host IP for FastAPI server |
| `API_PORT` | `8000` | HTTP port for FastAPI server |
| `DATA_DIR` | `./data` | Path to directory containing raw data files |
| `ARTIFACTS_DIR` | `./artifacts` | Directory for run execution artifacts and locks |
| `RANKING_METHOD` | `risk_v1` | Default ranking strategy (`risk_v1` or `baseline`) |
| `VISIT_LIMIT` | `15` | Target number of gateway visits per week |
| `RUN_LOCK_PATH` | `./artifacts/.run.lock` | OS file lock path for run serialization |
| `RUN_TIMEOUT_SECONDS` | `300` | Timeout before stale runs are marked `ORPHANED` |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## 7. Repository Layout

```
.
├── Makefile                          # Unified build, test, run, and docker targets
├── requirements.txt                  # Pinned dependencies
├── pyproject.toml                    # Python project & test configuration
├── Dockerfile                        # Multi-stage production container image
├── compose.yaml                      # Docker Compose service definition
├── validate_submission.py            # Official challenge validator
├── predictions.csv                   # Validated 120-row submission output
├── DECISIONS.md                      # Defended architectural decisions & roadmap
├── AI-USAGE.md                       # AI usage disclosure & error correction log
├── README.md                         # Comprehensive documentation
├── main.py                           # Unified CLI and API entry point
├── mcp_server.py                     # Model Context Protocol (MCP) stdio server
├── docs/                             # Detailed documentation
│   └── API.md                        # Complete REST API reference
├── app/                              # Core application package
│   ├── config.py                     # Central configuration & environment loading
│   ├── domain/                       # Core domain entities, models & exceptions
│   │   ├── models.py
│   │   ├── protocols.py
│   │   └── errors.py
│   ├── repositories/                 # Data access layer (Parquet & CSV)
│   │   ├── gateways.py
│   │   ├── telemetry.py
│   │   └── meter_reads.py
│   ├── features/                     # Point-in-time robust feature extraction
│   │   └── builder.py
│   ├── ranking/                      # Pluggable ranking strategies
│   │   ├── base.py
│   │   ├── risk_v1.py
│   │   └── baseline.py
│   ├── services/                     # Business logic and coordination
│   │   ├── ranking_service.py
│   │   ├── gateway_service.py
│   │   └── run_service.py
│   ├── explanations/                 # Operational explanation builder
│   │   └── builder.py
│   ├── validation/                   # Input & data quality validation
│   │   └── input.py
│   ├── output/                       # Atomic CSV and artifact writer
│   │   └── writer.py
│   └── api/                          # FastAPI web layer
│       ├── app.py
│       └── routes/
│           ├── health.py
│           ├── rankings.py
│           ├── gateways.py
│           └── runs.py
└── tests/                            # Comprehensive automated test suite
    ├── conftest.py
    ├── fixtures/
    ├── unit/
    ├── integration/
    ├── regression/
    └── e2e/
```
