# Gateway Visit Prioritisation System — Complete Project Documentation

> **LPDG Innovation Hub Selection Challenge 2026**  
> **Unified Part 1 (Deterministic Decision Engine) & Part 2 (Production Software Development Architecture)**

---

## 1. Executive Summary & Challenge Context

### 1.1 The Operational Challenge
LPDG operates a fleet of approximately 320 IoT smart meter radio gateways installed across rooftops, basements, and technical plant rooms in utility distribution regions. Each gateway aggregates hourly readings from 40 to 900 endpoint smart meters. 

When a gateway degrades or fails silently, downstream meters stop reporting. Unread meters lead to estimated billing errors, expensive manual read dispatches, customer dissatisfaction, and regulatory penalties. 

The operations department operates under strict physical and economic constraints:
- **Hard Operational Limit**: Exactly **15 technician visits per week**.
- **Wasted Visit Cost**: **€380** if a technician visits an operational gateway.
- **Unaddressed Failure Cost**: **€600/week** compounding for every week a malfunctioning gateway remains unvisited.
- **Decision Cadence**: Evaluated strictly every Monday at 00:00:00 UTC for the subsequent operational week.

### 1.2 System Mission
This repository delivers a deterministic, point-in-time, multi-signal decision engine (**Part 1**) integrated into a production-grade, modular, concurrency-safe **FastAPI** web service (**Part 2 — Software Development**).

---

## 2. Architectural Blueprint & Clean Architecture

The system is designed following Clean Architecture principles, ensuring that domain business rules remain completely decoupled from data storage mechanisms, HTTP delivery frameworks, and developer interfaces.

```
                                  ┌─────────────────────────────────────────┐
                                  │            Data Sources                 │
                                  │  telemetry/ (Parquet), master & meter   │
                                  └────────────────────┬────────────────────┘
                                                       │
                                                       ▼
                                  ┌─────────────────────────────────────────┐
                                  │           Repository Layer              │
                                  │  • TelemetryRepository (Partition Prune)│
                                  │  • GatewayRepository (Master metadata)  │
                                  │  • MeterReadRepository (Weekly counts)  │
                                  └────────────────────┬────────────────────┘
                                                       │
                                                       ▼
                                  ┌─────────────────────────────────────────┐
                                  │      Feature & Validation Engine        │
                                  │  • Strict Point-in-Time Cutoff Filter   │
                                  │  • Decoupled Windows: 21d Ref vs 7d Det │
                                  │  • Robust Statistics (Median / MAD)     │
                                  └────────────────────┬────────────────────┘
                                                       │
                        ┌──────────────────────────────┴──────────────────────────────┐
                        ▼                                                             ▼
         ┌─────────────────────────────┐                               ┌─────────────────────────────┐
         │  RankingStrategy Protocol   │                               │     OS Concurrency Lock     │
         │ • RiskRanker (risk_v1)      │                               │  • fcntl.flock serialization│
         │ • Baseline3SigmaRanker      │                               │  • Heartbeat crash recovery │
         └──────────────┬──────────────┘                               │  • Run artifact isolation   │
                        │                                              └──────────────┬──────────────┘
                        └──────────────────────────────┬──────────────────────────────┘
                                                       ▼
                                  ┌─────────────────────────────────────────┐
                                  │             Service Layer               │
                                  │  • RankingService (Weekly evaluation)   │
                                  │  • GatewayService (Diagnostics/reasons) │
                                  │  • RunService (Lifecycle orchestration) │
                                  └────────────────────┬────────────────────┘
                                                       │
                   ┌───────────────────────────────────┼───────────────────────────────────┐
                   ▼                                   ▼                                   ▼
         ┌───────────────────┐               ┌───────────────────┐               ┌───────────────────┐
         │  Part 1 CLI Engine│               │   FastAPI Web API │               │    MCP Server     │
         │ (predictions.csv) │               │ (/health, /weeks) │               │ (Stdio JSON-RPC)  │
         └───────────────────┘               └───────────────────┘               └───────────────────┘
```

---

## 3. Mathematical Scoring Formulation & Robust Feature Extraction

### 3.1 Strict Point-in-Time Windowing & Isolation
To prevent lookahead leakage and historical contamination:
- **Reference Window**: $[t_{\text{cutoff}} - 28\text{d}, t_{\text{cutoff}} - 7\text{d})$ (21 days of historical baseline).
- **Detection Window**: $[t_{\text{cutoff}} - 7\text{d}, t_{\text{cutoff}})$ (7 days of recent telemetry evaluation).
- **Isolation Guarantee**: Severe recent failures cannot contaminate or inflate historical reference statistics.

### 3.2 Non-Parametric Robust Statistics (Median / MAD)
For each telemetry metric $m \in \{\text{offline\_duration\_sec}, \text{disconnection\_cnt}, \text{reboot\_cnt}\}$:

$$\text{Median}_m = \text{median}(X_{\text{ref}, m})$$

$$\text{MAD}_m = \text{median}(|X_{\text{ref}, m} - \text{Median}_m|)$$

$$\text{Scale}_m = \max\left(\text{MAD}_m \times 1.4826, \text{ScaleFloor}_m\right)$$

- **Physical Scale Floors**: $\text{ScaleFloor}_{\text{offline}} = 60.0\,\text{s}$, $\text{ScaleFloor}_{\text{counts}} = 1.0$. This prevents zero-MAD singularities from turning isolated benign events into artificial $10,000\sigma$ alerts.
- **Robust Z-Score**: $z_{i, m} = \min\left(10.0, \frac{x_{i, m} - \text{Median}_m}{\text{Scale}_m}\right)$ for hourly records in the detection window.

### 3.3 Composite Score Calculation (0 to 100 Scale)

$$\text{Final Score} = 0.70 \times \text{Telemetry Risk} + 0.25 \times \text{Meter Impact} + 0.05 \times \text{Data Confidence}$$

1. **Telemetry Risk ($0 - 100$)**:
   $$\text{Telemetry Risk} = \left(0.45 \times P + 0.35 \times S + 0.20 \times R\right) \times M_{\text{imp}}$$
   - **Persistence ($P$)**: Fraction of anomalous hours ($z > 3.0$) in the detection window ($0 - 100$).
   - **Severity ($S$)**: Mean robust z-score across flagged hours normalized to $[0, 100]$ ($\text{mean}(z) / 10.0 \times 100$).
   - **Recency ($R$)**: Exponential time-decay weight favoring anomalies occurring within the final 48 hours.
   - **Supervisory Multiplier ($M_{\text{imp}}$)**: Bounded multiplicative booster ($\le 1.15\times$) derived from `reboot_importance` and `no_conn_importance`.

2. **Downstream Meter Impact ($0 - 100$)**:
   $$\text{Meter Impact} = \left(0.60 \times (1 - \text{Success Ratio}) + 0.40 \times \text{Degradation}\right) \times \min\left(1.0, \frac{\ln(1 + \text{Meters})}{\ln(1 + 500)}\right) \times 100$$
   - Sublinear logarithmic exposure weighting ensures customer-facing risk is prioritized without allowing giant sites to permanently starve smaller regional gateways.

3. **Data Confidence ($0 - 100$)**:
   - Scores 100 for full 21-day reference ($\ge 14$ days) and 7-day detection ($\ge 5$ days); discounted proportionally for degraded histories.
   - **Dynamic Weight Rebalancing**: If meter-read data is missing, weights rebalance to $\frac{0.70}{0.75} \times \text{Risk} + \frac{0.05}{0.75} \times \text{Confidence}$.

4. **Deterministic 4-Key Tie Breaking**:
   Gateways are ranked deterministically by the tuple:
   $$\text{Sort Key} = \left(-\text{final\_score}, -\text{exposure\_meters}, -\text{total\_recent\_offline\_sec}, \text{gateway\_id}\right)$$

---

## 4. Part 1 Compliance & Submission Validation

The pipeline produces the submission file `predictions.csv`, which has been verified against the official `validate_submission.py` validator with **zero errors**.

### Submission Attributes
- **Total Rows**: Exactly 120 rows (15 visits $\times$ 8 evaluated Mondays: `2026-02-02` to `2026-03-23`).
- **Required Columns**: `week_start, rank, gateway_id, score, reason`.
- **Reason Constraints**: Non-empty, fully contextualized, operations-ready strings strictly $\le 300$ characters.
- **Data Confidentiality**: Raw telemetry datasets (104 MB) are strictly excluded from source control via `.gitignore`.

```bash
# Verify submission output
python3 validate_submission.py predictions.csv
# Output: predictions.csv: OK (15 ranked gateways for each of 8 weeks)
```

---

## 5. Part 2 REST API Reference (FastAPI)

The production web service runs on **FastAPI** with automatic OpenAPI 3.1 specifications.

- **Base URL**: `http://localhost:8000`
- **Interactive Swagger UI**: `http://localhost:8000/docs`
- **ReDoc Documentation**: `http://localhost:8000/redoc`
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

### Endpoint Catalog

| Method | Path | Summary | Success Status |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | System health & data directory readiness check | `200 OK` |
| `GET` | `/api/v1/weeks/{week_start}/predictions` | Get top 15 ranked gateways for a given Monday | `200 OK` |
| `GET` | `/api/v1/predictions` | Get top 15 ranked gateways for latest scored week | `200 OK` |
| `GET` | `/api/v1/weeks/{week_start}/gateways/{gateway_id}` | Detailed evaluation and explanation for a gateway | `200 OK` |
| `GET` | `/api/v1/gateways/{gateway_id}` | Direct evaluation for a gateway (latest or specified week) | `200 OK` |
| `POST`| `/api/v1/runs` | Trigger a new prioritisation run with concurrency locking | `201 Created` |
| `GET` | `/api/v1/runs/{run_id}` | Retrieve run metadata, status, and artifact paths | `200 OK` |

### Example cURL Queries

#### 1. System Health Check
```bash
curl -X GET "http://localhost:8000/health"
```
**Response (`200 OK`)**:
```json
{
  "status": "healthy",
  "timestamp": "2026-03-23T10:00:00+00:00",
  "version": "0.2.0",
  "environment": "development",
  "data_dir_ready": true,
  "ranking_method": "risk_v1"
}
```

#### 2. Retrieve Weekly Predictions
```bash
curl -X GET "http://localhost:8000/api/v1/weeks/2026-03-23/predictions"
```
**Response (`200 OK`)**:
```json
{
  "week_start": "2026-03-23",
  "ranking_method": "risk_v1",
  "run_id": null,
  "count": 15,
  "predictions": [
    {
      "rank": 1,
      "gateway_id": "0202CB0A6B1F",
      "score": 88.4215,
      "reason": "High priority (Rank 1): 24 abnormal offline duration hour(s) in last 7 days vs 21-day baseline. Meter reads fell to 78% across 450 expected meters.",
      "ranking_method": "risk_v1"
    }
  ]
}
```

#### 3. Inspect Specific Gateway (Ranked, Unranked, or Ineligible)
```bash
curl -X GET "http://localhost:8000/api/v1/gateways/0202CB0A6B1F?week_start=2026-02-02"
```
**Response (`200 OK`)**:
```json
{
  "gateway_id": "0202CB0A6B1F",
  "week_start": "2026-02-02",
  "status": "ELIGIBLE_UNRANKED",
  "rank": 151,
  "score": 21.4378,
  "ranking_method": "risk_v1",
  "reason": "Eligible (Rank 151, Score 21.44) below weekly quota limit (15). Observed 2 abnormal offline duration hour(s). Meter read success at 98%.",
  "is_eligible": true,
  "details": {
    "tenant": "tenant_a",
    "region": "Sachsen",
    "n_meters_installed": 166,
    "score_breakdown": {
      "final_score": 21.4378,
      "telemetry_risk": 23.0574,
      "meter_impact": 1.1903,
      "data_confidence": 100.0
    }
  }
}
```

#### 4. Trigger Execution Run
```bash
curl -X POST "http://localhost:8000/api/v1/runs" \
     -H "Content-Type: application/json" \
     -d '{"weeks": ["2026-03-16", "2026-03-23"], "ranking_method": "risk_v1"}'
```
**Response (`201 Created`)**:
```json
{
  "run_id": "run_20260323_120000_a1b2c3",
  "status": "SUCCEEDED",
  "ranking_method": "risk_v1",
  "requested_weeks": ["2026-03-16", "2026-03-23"],
  "started_at": "2026-03-23T12:00:00+00:00",
  "completed_at": "2026-03-23T12:00:05+00:00",
  "artifact_paths": {
    "predictions_csv": "/app/artifacts/runs/run_20260323_120000_a1b2c3/predictions.csv",
    "metadata_json": "/app/artifacts/runs/run_20260323_120000_a1b2c3/metadata.json"
  }
}
```

---

## 6. Concurrency Control, Run Isolation & Crash Recovery

1. **OS File Lock**: `RunService` acquires an exclusive, non-blocking lock on `artifacts/.run.lock` using `fcntl.flock`. If a concurrent execution is attempted, the second request immediately returns **`409 Conflict`**.
2. **Artifact Isolation**: Run artifacts are strictly isolated under `artifacts/runs/<run_id>/predictions.csv` and never mutate or overwrite the root `./predictions.csv` used for challenge submission.
3. **Heartbeat & Orphaned Run Recovery**: Runs record continuous heartbeat timestamps. In the event of an unhandled host process crash (e.g. `SIGKILL`), subsequent requests detect stale locks exceeding `RUN_TIMEOUT_SECONDS` (300s) and transition the state to `ORPHANED`.

---

## 7. Model Context Protocol (MCP) Server

The repository includes a standard Model Context Protocol (MCP) stdio server (`mcp_server.py`) enabling seamless integration with AI coding assistants and IDE tool ecosystems:

- **`prioritise_visits`**: Executes full 8-week prioritisation pipeline and writes validated CSV.
- **`inspect_gateway`**: Diagnoses telemetry, coverage, and rank status for a specific gateway on any given week.
- **`validate_predictions`**: Runs the schema validator programmatically.

```bash
# Test MCP server tools list
echo '{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}' | python3 mcp_server.py
```

---

## 8. Automated Testing & Verification Suite

The repository features **48 automated tests** passing with 100% success rate:

- **Unit Tests (`tests/unit/`)**:
  - `test_boundaries_and_isolation.py`: Strict half-open intervals and reference baseline contamination protection.
  - `test_robust_stats_and_weights.py`: Zero-MAD scale floors, missing meter data weight rebalancing, confidence penalties.
  - `test_tie_breaking.py`: Deterministic 4-key sort stability.
  - `test_ranking_strategies.py`: Strategy factory registry and scoring bounds.
  - `test_repositories.py`: Partition pruning, column filtering, ID normalisation.
  - `test_explanations.py`: Reason length constraint ($\le 300$ chars) and clarity.
  - `test_run_locking.py`: Concurrency mutex locking.
  - `test_validation.py`: Input format and date validators.
- **Integration Tests (`tests/integration/`)**:
  - `test_api_endpoints.py`: All HTTP routes, status codes, query params, and aliases.
  - `test_gateway_service.py`: Evaluation of ranked, eligible unranked, and ineligible gateways.
  - `test_ranking_service.py`: Weekly rank computation and scoring.
  - `test_pipeline_integration.py`: Full end-to-end 8-week pipeline against synthetic test fixtures.
- **Regression Tests (`tests/regression/`)**:
  - `test_edge_cases.py`: Orphaned run recovery and zero-telemetry gateway handling.
- **End-to-End Tests (`tests/e2e/`)**:
  - `test_e2e_flow.py`: Full HTTP execution flow and schema validation.

```bash
# Run complete test suite
pytest -v
# Output: 48 passed in ~10s
```

---

## 9. Configuration Reference

Environment variables can be supplied via environment or `.env` file (see `.env.example`):

| Variable | Default | Description |
| :--- | :--- | :--- |
| `APP_ENV` | `development` | Environment mode (`development`, `production`, `test`) |
| `API_HOST` | `0.0.0.0` | Host IP for FastAPI server |
| `API_PORT` | `8000` | HTTP port for FastAPI server |
| `DATA_DIR` | `./data` | Directory holding `gateway_master.csv`, `telemetry/`, etc. |
| `ARTIFACTS_DIR` | `./artifacts` | Root directory for isolated run outputs and locks |
| `RANKING_METHOD` | `risk_v1` | Default ranking strategy (`risk_v1` or `baseline`) |
| `VISIT_LIMIT` | `15` | Target number of gateway visits per week |
| `RUN_LOCK_PATH` | `./artifacts/.run.lock` | OS file lock path for run serialization |
| `RUN_TIMEOUT_SECONDS`| `300` | Timeout before stale runs are marked `ORPHANED` |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## 10. Operational Runbook & Commands

### 10.1 Local Execution
```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run deterministic pipeline
make run
# or: python3 main.py --data data --out predictions.csv

# 3. Validate submission
make validate
# or: python3 validate_submission.py predictions.csv

# 4. Start FastAPI server
make api
# or: python3 main.py --serve --host 0.0.0.0 --port 8000

# 5. Run test suite
make test
# or: pytest -v
```

### 10.2 Docker & Docker Compose
```bash
# Build container image
make docker-build

# Run API in isolated container with data mounted read-only
make docker-run

# Or run with Docker Compose
docker compose up --build
```
