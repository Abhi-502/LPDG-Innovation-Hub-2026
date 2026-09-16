# Gateway Visit Prioritisation System (Unified Part 1 & Part 2)

> **LPDG Innovation Hub Selection Challenge 2026 — Deterministic Prioritisation Engine & Production Software Development API**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688.svg)](https://fastapi.tiangolo.com)
[![Pytest](https://img.shields.io/badge/tests-48%20passed-brightgreen.svg)](https://docs.pytest.org/)
[![Schema Validated](https://img.shields.io/badge/predictions.csv-100%25%20compliant-success.svg)](file:///Users/macbook/Desktop/CHALLENGE/validate_submission.py)
[![Walkthrough Video](https://img.shields.io/badge/Walkthrough%20Video-8%20mins%20(1080p%2F720p)-orange.svg)](walkthrough_demo.mp4)
[![Candidate Resume](https://img.shields.io/badge/23091A0502.pdf-blueviolet.svg)](23091A0502.pdf)

---

## 📹 Video Walkthrough & Candidate Submission Materials

- 🎬 **8-Minute Technical Walkthrough**: [**`walkthrough_demo.mp4`** (Click to view / download)](walkthrough_demo.mp4)
- 📄 **Candidate Resume (SDE)**: [**`23091A0502.pdf`**](23091A0502.pdf)
- 📝 **Full Presentation Script & Timing Guide**: [**`VIDEO_RECORDING_SCRIPT.md`**](VIDEO_RECORDING_SCRIPT.md)

---

## 1. Executive Summary & Challenge Context

LPDG operates an IoT radio network of approximately 320 smart meter gateways installed across residential and commercial buildings. Each gateway relays hourly readings for 40 to 900 smart meters. Silent gateway failures result in unread meters, estimated bills, manual read dispatches, and regulatory non-compliance.

### Operational Constraints & Economics
- **Weekly Dispatch Limit**: Exactly **15 technician visits per week**.
- **Wasted Visit Cost**: **€380** if a technician is sent to a healthy gateway.
- **Unaddressed Outage Cost**: **€600/week** compounding for every week a broken gateway remains unaddressed.
- **Decision Schedule**: Evaluated strictly every Monday at 00:00:00 UTC for the subsequent week.

This repository provides a fully unified solution:
- **Part 1 (Deterministic Core Engine)**: Point-in-time multi-signal scoring, robust statistics (Median/MAD with scale floors), strict window isolation, and deterministic tie-breaking.
- **Part 2 (Software Development Production Architecture)**: Layered clean architecture, modular **FastAPI** REST API, OpenAPI/Swagger documentation, pluggable `RankingStrategy` registry, OS-level concurrency locking (`fcntl.flock`), and an Stdio Model Context Protocol (MCP) server.

---

## 2. System Architecture & Layering

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
                                  │  Feature & Quality Gate   │
                                  │  21d Ref vs 7d Det (MAD)  │
                                  └─────────────┬─────────────┘
                                                │
                        ┌───────────────────────┴───────────────────────┐
                        ▼                                               ▼
         ┌─────────────────────────────┐                 ┌─────────────────────────────┐
         │  RankingStrategy Protocol   │                 │     OS Run Lock (fcntl)     │
         │ • RiskRanker (risk_v1)      │                 │  • Atomic run serialization │
         │ • Baseline3SigmaRanker      │                 │  • Run artifact isolation   │
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
         │ (predictions.csv) │        │ (/health, /weeks) │        │  (Stdio JSON-RPC) │
         └───────────────────┘        └───────────────────┘        └───────────────────┘
```

---

## 3. Quick Start & Execution Guide

### 3.1 Setup Environment
```bash
# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install pinned dependencies
pip install -r requirements.txt
```

### 3.2 Part 1: Execute CLI Pipeline (One Command)
Produces the official submission file `predictions.csv`:
```bash
# Standard execution (reads ./data and generates ./predictions.csv)
make run
# or:
python3 main.py --data data --out predictions.csv

# Running on custom / unseen evaluation data with specific weeks:
python3 main.py --data "/path/to/custom/data" --weeks 2026-04-06,2026-04-13 --out predictions.csv
```

### 3.3 Validate Submission File
Executes the official challenge schema validator:
```bash
make validate
# or:
python3 validate_submission.py predictions.csv
```
**Output**:
```
predictions.csv: OK
  15 ranked gateways for each of 8 weeks, 2026-02-02 to 2026-03-23
```

### 3.4 Part 2: Start FastAPI Web Service
```bash
make api
# or:
python3 main.py --serve --host 0.0.0.0 --port 8000
```
- **Interactive Swagger UI**: [`http://localhost:8000/docs`](http://localhost:8000/docs)
- **ReDoc Documentation**: [`http://localhost:8000/redoc`](http://localhost:8000/redoc)
- **OpenAPI Schema**: [`http://localhost:8000/openapi.json`](http://localhost:8000/openapi.json)

### 3.5 Run Model Context Protocol (MCP) Stdio Server
```bash
python3 mcp_server.py
```

### 3.6 Execute Automated Test Suite (48 Tests)
```bash
make test
# or:
pytest -v
```

### 3.7 Run in Isolated Docker Container
```bash
# Build Docker image
make docker-build

# Run API container with data mounted read-only
make docker-run

# Or run via Docker Compose
docker compose up --build
```

---

## 4. Scoring & Ranking Formulation

All score components are normalized to an explicit **0 to 100** composite scale:

$$\text{Final Score} = 0.70 \times \text{Telemetry Risk} + 0.25 \times \text{Meter Impact} + 0.05 \times \text{Data Confidence}$$

1. **Telemetry Risk ($0 - 100$)**:
   $$\text{Telemetry Risk} = (0.45 \times P + 0.35 \times S + 0.20 \times R) \times M_{\text{imp}}$$
   - **Persistence ($P$)**: Fraction of detection hours ($z > 3.0$) flagged as anomalous ($0 - 100$).
   - **Severity ($S$)**: Mean robust z-score $\left(\frac{x - \text{Median}}{\text{MAD} \times 1.4826}\right)$ normalized to $[0, 100]$ (capped at $10.0\sigma$).
   - **Recency ($R$)**: Exponential time-decay weight favoring failures in the final 48 hours.
   - **Scale Floors**: Physical minimum scale floors ($60.0\,\text{s}$ for offline duration, $1.0$ for event counts) prevent zero-MAD false alarms.

2. **Downstream Meter Impact ($0 - 100$)**:
   $$\text{Meter Impact} = \left(0.60 \times (1 - \text{Read Success}) + 0.40 \times \text{Degradation}\right) \times \min\left(1.0, \frac{\ln(1 + \text{Meters})}{\ln(1 + 500)}\right) \times 100$$
   - Sublinear logarithmic exposure scaling ensures customer impact is prioritized without mega-sites monopolizing the queue.

3. **Data Confidence ($0 - 100$)**:
   - Scores $100$ for full 21-day reference and 7-day detection coverage; proportionally discounted when coverage is degraded. Dynamically rebalances weights if meter data is missing.

4. **Deterministic 4-Key Tie Breaking**:
   $$\text{Sort Key} = \left(-\text{final\_score}, -\text{exposure\_meters}, -\text{total\_recent\_offline\_sec}, \text{gateway\_id}\right)$$
   Guarantees 100% byte-for-byte reproducible rank order regardless of row order or operating system.

---

## 5. REST API Endpoints Overview

| Method | Endpoint | Description | Status Code |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | System health check and data directory readiness | `200 OK` |
| `GET` | `/api/v1/weeks/{week_start}/predictions` | Retrieve top 15 ranked gateways for a given Monday cutoff | `200 OK` |
| `GET` | `/api/v1/predictions` | Retrieve top 15 ranked gateways for latest scored week | `200 OK` |
| `GET` | `/api/v1/weeks/{week_start}/gateways/{gateway_id}` | Diagnostic evaluation for ranked, unranked, or ineligible gateways | `200 OK` |
| `GET` | `/api/v1/gateways/{gateway_id}` | Direct diagnostic evaluation for a gateway (latest or specified week) | `200 OK` |
| `POST`| `/api/v1/runs` | Trigger a new prioritisation run with concurrency locking (`409 Conflict`) | `201 Created` |
| `GET` | `/api/v1/runs/{run_id}` | Retrieve execution run status, timestamps, and isolated artifact paths | `200 OK` |

For full request/response schemas and curl examples, see [docs/API.md](docs/API.md).

---

## 6. Concurrency Control & Run Artifact Isolation

1. **Kernel Mutex Lock**: `RunService` acquires an exclusive, non-blocking lock on `artifacts/.run.lock` using `fcntl.flock`. Overlapping concurrent runs receive an immediate **`409 Conflict`**.
2. **Artifact Isolation**: REST API runs write exclusively to `artifacts/runs/<run_id>/predictions.csv` and `metadata.json`, leaving root `./predictions.csv` unmutated for CLI submissions.
3. **Heartbeat & Crash Recovery**: Periodic heartbeat updates ensure that unexpected process crashes (`SIGKILL`) are detected after 300s and transitioned to `ORPHANED`.

---

## 7. Configuration Reference

| Variable | Default | Description |
| :--- | :--- | :--- |
| `APP_ENV` | `development` | Environment mode (`development`, `production`, `test`) |
| `API_HOST` | `0.0.0.0` | Host IP for FastAPI server |
| `API_PORT` | `8000` | HTTP port for FastAPI server |
| `DATA_DIR` | `./data` | Path to directory containing raw dataset files |
| `ARTIFACTS_DIR` | `./artifacts` | Root directory for isolated run outputs and locks |
| `RANKING_METHOD` | `risk_v1` | Default ranking strategy (`risk_v1` or `baseline`) |
| `VISIT_LIMIT` | `15` | Target number of gateway visits per week |
| `RUN_LOCK_PATH` | `./artifacts/.run.lock` | OS file lock path for run serialization |
| `RUN_TIMEOUT_SECONDS`| `300` | Timeout before stale runs are marked `ORPHANED` |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## 8. Detailed Documentation Index

- **[23091A0502.pdf](23091A0502.pdf)**: Candidate Resume (Software Development Engineer).
- **[PROJECT_DOCUMENTATION.md](PROJECT_DOCUMENTATION.md)**: Complete system design, operational ROI, and architectural blueprint.
- **[PROCESS_AND_TERMINOLOGY_GUIDE.md](PROCESS_AND_TERMINOLOGY_GUIDE.md)**: Exhaustive domain glossary, formulas, and stage-by-stage execution map.
- **[VIDEO_RECORDING_SCRIPT.md](VIDEO_RECORDING_SCRIPT.md)**: 6 to 8-minute presentation script, timing breakdown, and speaking guide.
- **[DECISIONS.md](DECISIONS.md)**: 5 defended architectural choices, Part 2 track defense, and two-week roadmap.
- **[AI-USAGE.md](AI-USAGE.md)**: AI usage disclosure & log of 5 concrete corrected errors.
- **[docs/API.md](docs/API.md)**: Full REST API specification with cURL examples.
