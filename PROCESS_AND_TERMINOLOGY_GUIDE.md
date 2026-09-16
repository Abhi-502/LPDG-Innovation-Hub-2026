# Gateway Prioritisation Engine — Terminology, Mathematical Concepts & Pipeline Process Guide

> **LPDG Innovation Hub Selection Challenge 2026**  
> **Comprehensive Guide to Domain Terms, Mathematical Formulations, Architecture Layers, and Execution Lifecycle**

---

## 1. Executive Process Map

The diagram below illustrates the end-to-end data lifecycle, highlighting exactly where every domain term, statistical formula, and architectural gate is executed across the codebase.

```
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
STAGE 1: INGESTION & DATA DISCOVERY (`app/repositories/`)
───────────────────────────────────────────────────────────────────────────────────────────────────────────
  [Parquet Telemetry Files]   [Gateway Master CSV]   [Meter Read Success CSV]
             │                         │                        │
             ▼                         ▼                        ▼
  • Monthly Partition Pruning  • 12-Hex Normalisation   • Gateway Metric Aggregation
  • PIT Cutoff Filtering       • Active/Decom Filter    • Baseline Read Success Ratios
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
                                          │
                                          ▼
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
STAGE 2: QUALITY ASSESSMENT GATE (`app/validation/`)
───────────────────────────────────────────────────────────────────────────────────────────────────────────
  • Evaluates Historical Reference Days (>= 14d required for full quality)
  • Evaluates Detection Days (>= 5d required for full quality)
  • Calculates Confidence Penalty (0.0 to 1.0) & Disqualification Flags
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
                                          │
                                          ▼
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
STAGE 3: WINDOW ISOLATION & FEATURE EXTRACTION (`app/features/builder.py`)
───────────────────────────────────────────────────────────────────────────────────────────────────────────
  ┌──────────────────────────────────────────────┬──────────────────────────────────────────────┐
  │ Reference Window [cutoff - 28d, cutoff - 7d) │ Detection Window [cutoff - 7d, cutoff)       │
  │ • Compute Median & MAD                       │ • Calculate Robust Z-Scores (capped @ 10.0σ) │
  │ • Apply Physical Scale Floors (60s, 1.0)     │ • Flag Anomaly Hours (z > 3.0σ)              │
  └──────────────────────────────────────────────┴──────────────────────────────────────────────┘
                                          │
                                          ▼
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
STAGE 4: COMPOSITE RISK SCORING (`app/ranking/risk_v1.py`)
───────────────────────────────────────────────────────────────────────────────────────────────────────────
  • Telemetry Risk (0-100) = (0.45*Persistence + 0.35*Severity + 0.20*Recency) * Importance Multiplier
  • Meter Impact   (0-100) = (0.60*FailureRatio + 0.40*Degradation) * log1p(Meters)/log1p(500) * 100
  • Data Confidence(0-100) = (1.0 - QualityPenalty) * 100
  • Final Composite Score  = 0.70*TelemetryRisk + 0.25*MeterImpact + 0.05*DataConfidence
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
                                          │
                                          ▼
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
STAGE 5: DETERMINISTIC RANKING & REASON BUILDER (`app/ranking/`, `app/explanations/`)
───────────────────────────────────────────────────────────────────────────────────────────────────────────
  • Sort Key: (-final_score, -exposure_meters, -total_recent_offline_sec, gateway_id)
  • Slice Top 15 Priority Visits
  • Generate Operations Reason (<= 300 characters) specifying failure mode, persistence & meters
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
                                          │
                                          ▼
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
STAGE 6: OUTPUT GENERATION & DELIVERY (`app/output/`, `app/api/`, `mcp_server.py`)
───────────────────────────────────────────────────────────────────────────────────────────────────────────
  • Atomic CSV Write to `predictions.csv` (120 rows across 8 weeks)
  • REST API Endpoints (`/health`, `/weeks/{date}/predictions`, `/gateways/{id}`)
  • OS Concurrency Locking (`fcntl.flock`) & Isolated Run Artifacts (`artifacts/runs/<run_id>/`)
  • Model Context Protocol (MCP) Stdio Tools for AI and IDE integration
═══════════════════════════════════════════════════════════════════════════════════════════════════════════
```

---

## 2. Comprehensive Terminology & Domain Glossary

### 2.1 Domain & Hardware Terms

| Term | Definition | Where It Is Handled |
| :--- | :--- | :--- |
| **Gateway (`gateway_id`)** | An IoT data concentrator installed in plant rooms, basements, or rooftops that receives radio transmissions from smart meters and relays them over cellular/IP to central servers. Identified by a 12-digit hexadecimal string (e.g., `0202CB0A6B1F`). | [`app/domain/models.py`](file:///Users/macbook/Desktop/CHALLENGE/app/domain/models.py), [`app/repositories/gateways.py`](file:///Users/macbook/Desktop/CHALLENGE/app/repositories/gateways.py) |
| **Smart Meter** | An electricity, gas, or water meter that transmits consumption readings to a local gateway. | [`app/repositories/meter_reads.py`](file:///Users/macbook/Desktop/CHALLENGE/app/repositories/meter_reads.py) |
| **Meter Fleet Exposure (`exposure_meters`)** | The number of downstream meters relying on a given gateway. Represents the business scale / customer impact of a failure. Evaluated as $\max(\text{meters\_expected}, \text{n\_meters\_installed})$. | [`app/ranking/risk_v1.py`](file:///Users/macbook/Desktop/CHALLENGE/app/ranking/risk_v1.py), [`app/domain/models.py`](file:///Users/macbook/Desktop/CHALLENGE/app/domain/models.py) |
| **Field Visit** | An on-site dispatch of a field engineer/technician to repair, reset, or replace a faulty gateway. Limited to a strict quota of **15 visits per week**. | [`main.py`](file:///Users/macbook/Desktop/CHALLENGE/main.py), [`app/services/ranking_service.py`](file:///Users/macbook/Desktop/CHALLENGE/app/services/ranking_service.py) |
| **Wasted Visit Cost (€380)** | The economic cost incurred when a technician is dispatched to an operational/healthy gateway that did not need maintenance. | [`DECISIONS.md`](file:///Users/macbook/Desktop/CHALLENGE/DECISIONS.md), [`PROJECT_DOCUMENTATION.md`](file:///Users/macbook/Desktop/CHALLENGE/PROJECT_DOCUMENTATION.md) |
| **Unaddressed Failure Cost (€600/wk)** | The compounding penalty incurred for every week a malfunctioning gateway remains unvisited in the field. | [`DECISIONS.md`](file:///Users/macbook/Desktop/CHALLENGE/DECISIONS.md), [`PROJECT_DOCUMENTATION.md`](file:///Users/macbook/Desktop/CHALLENGE/PROJECT_DOCUMENTATION.md) |

---

### 2.2 Temporal & Windowing Terms

| Term | Definition | Where It Is Handled |
| :--- | :--- | :--- |
| **Decision Cutoff (`cutoff_utc`)** | The exact point in time (every Monday at 00:00:00 UTC) at which prioritisation decisions are calculated for the upcoming week. | [`app/config.py`](file:///Users/macbook/Desktop/CHALLENGE/app/config.py), [`app/services/ranking_service.py`](file:///Users/macbook/Desktop/CHALLENGE/app/services/ranking_service.py) |
| **Point-in-Time (PIT) Filtering** | Strict filtering that guarantees the model only accesses data with timestamps $t < t_{\text{cutoff}}$. Future data $t \ge t_{\text{cutoff}}$ is strictly excluded to prevent lookahead data leakage. | [`app/repositories/telemetry.py`](file:///Users/macbook/Desktop/CHALLENGE/app/repositories/telemetry.py), [`app/features/builder.py`](file:///Users/macbook/Desktop/CHALLENGE/app/features/builder.py) |
| **Historical Reference Window** | The 21-day trailing period $[t_{\text{cutoff}} - 28\text{d}, t_{\text{cutoff}} - 7\text{d})$ used to compute historical baseline normal statistics (Median and MAD). | [`app/features/builder.py`](file:///Users/macbook/Desktop/CHALLENGE/app/features/builder.py) |
| **Recent Detection Window** | The 7-day trailing period $[t_{\text{cutoff}} - 7\text{d}, t_{\text{cutoff}})$ evaluated for recent anomalous deviations and persistent degradation. | [`app/features/builder.py`](file:///Users/macbook/Desktop/CHALLENGE/app/features/builder.py) |
| **Window Decoupling / Isolation** | The architectural separation between the 21-day reference and 7-day detection intervals. Prevents severe recent failures (e.g. 7 days offline) from inflating the baseline mean/variance and diluting their own anomaly score. | [`app/features/builder.py`](file:///Users/macbook/Desktop/CHALLENGE/app/features/builder.py), [`tests/unit/test_boundaries_and_isolation.py`](file:///Users/macbook/Desktop/CHALLENGE/tests/unit/test_boundaries_and_isolation.py) |
| **Scored Weeks Window** | The 8 official challenge Mondays spanning 2 February 2026 to 23 March 2026. | [`app/config.py`](file:///Users/macbook/Desktop/CHALLENGE/app/config.py), [`validate_submission.py`](file:///Users/macbook/Desktop/CHALLENGE/validate_submission.py) |

---

### 2.3 Statistical & Mathematical Terms

| Term | Mathematical Definition | Where It Is Handled |
| :--- | :--- | :--- |
| **Median** | The 50th percentile of historical reference values: $\text{Median} = \text{median}(X_{\text{ref}})$. Non-parametric center resisting outlier corruption. | [`app/features/builder.py:compute_median_mad`](file:///Users/macbook/Desktop/CHALLENGE/app/features/builder.py) |
| **Median Absolute Deviation (MAD)** | $\text{MAD} = \text{median}(|X_{\text{ref}} - \text{Median}|)$. A robust estimator of statistical dispersion. | [`app/features/builder.py:compute_median_mad`](file:///Users/macbook/Desktop/CHALLENGE/app/features/builder.py) |
| **Normal Consistency Factor (1.4826)** | Multiplier applied to MAD ($\text{Scale} = \text{MAD} \times 1.4826$) to make it an asymptotically unbiased estimator of standard deviation for normal distributions. | [`app/features/builder.py`](file:///Users/macbook/Desktop/CHALLENGE/app/features/builder.py) |
| **Physical Scale Floor (`min_scale_floor`)** | Minimum threshold enforcing $\text{Scale} \ge \text{Floor}$ ($60.0\,\text{s}$ for offline duration, $1.0$ for event counts). Protects quiet baselines ($\text{MAD}=0$) against division-by-zero or false-alarm explosions ($z=10,000\sigma$). | [`app/config.py`](file:///Users/macbook/Desktop/CHALLENGE/app/config.py), [`app/features/builder.py`](file:///Users/macbook/Desktop/CHALLENGE/app/features/builder.py) |
| **Robust Z-Score ($z$)** | $z = \min\left(10.0, \frac{x - \text{Median}}{\text{Scale}}\right)$. Number of robust standard deviations an hourly observation deviates from the gateway's own reference baseline. | [`app/features/builder.py`](file:///Users/macbook/Desktop/CHALLENGE/app/features/builder.py) |
| **Anomaly Hour Threshold ($z > 3.0$)** | Threshold at which an individual hour is classified as statistically anomalous ($\approx 99.73\%$ confidence under normal behavior). | [`app/config.py:anomaly_z_threshold`](file:///Users/macbook/Desktop/CHALLENGE/app/config.py), [`app/features/builder.py`](file:///Users/macbook/Desktop/CHALLENGE/app/features/builder.py) |
| **Persistence Ratio ($P$)** | Fraction of detection hours flagged as anomalous: $P = \frac{\text{flagged\_hours}}{\text{total\_detection\_hours}} \in [0.0, 1.0]$. Distinguishes sustained failures from isolated transient blips. | [`app/domain/models.py`](file:///Users/macbook/Desktop/CHALLENGE/app/domain/models.py), [`app/ranking/risk_v1.py`](file:///Users/macbook/Desktop/CHALLENGE/app/ranking/risk_v1.py) |
| **Anomaly Severity ($S$)** | Mean robust z-score across all flagged anomaly hours, normalized to $[0, 100]$: $S = \min\left(1.0, \frac{\text{mean}(z)}{10.0}\right) \times 100$. | [`app/ranking/risk_v1.py`](file:///Users/macbook/Desktop/CHALLENGE/app/ranking/risk_v1.py) |
| **Exponential Recency Score ($R$)** | Time-decay weighting favoring failures in the final 48 hours: $w(t) = \exp\left(-\frac{\Delta t}{48.0}\right)$, giving higher urgency to current active breakdowns. | [`app/ranking/risk_v1.py`](file:///Users/macbook/Desktop/CHALLENGE/app/ranking/risk_v1.py) |
| **Importance Multiplier ($M_{\text{imp}}$)** | Multiplicative booster ($\le 1.15\times$) derived from `reboot_importance` and `no_conn_importance` flags to avoid double-counting raw counters. | [`app/ranking/risk_v1.py`](file:///Users/macbook/Desktop/CHALLENGE/app/ranking/risk_v1.py) |

---

### 2.4 Scoring, Ranking & Tie-Breaking Terms

| Term | Mathematical Formulation | Where It Is Handled |
| :--- | :--- | :--- |
| **Telemetry Risk ($0 - 100$)** | $\text{Risk} = (0.45 \times P + 0.35 \times S + 0.20 \times R) \times M_{\text{imp}}$ | [`app/ranking/risk_v1.py:compute_telemetry_risk`](file:///Users/macbook/Desktop/CHALLENGE/app/ranking/risk_v1.py) |
| **Meter Impact ($0 - 100$)** | $\text{Impact} = \left(0.60 \times (1 - \text{Success}) + 0.40 \times \text{Degradation}\right) \times \min\left(1.0, \frac{\ln(1 + \text{Meters})}{\ln(1 + 500)}\right) \times 100$ | [`app/ranking/risk_v1.py:compute_meter_impact`](file:///Users/macbook/Desktop/CHALLENGE/app/ranking/risk_v1.py) |
| **Data Confidence ($0 - 100$)** | $\text{Confidence} = (1.0 - \text{QualityPenalty}) \times 100$. Deducts penalties if reference history has $< 14$ days or detection has $< 5$ days. | [`app/ranking/risk_v1.py:compute_data_confidence`](file:///Users/macbook/Desktop/CHALLENGE/app/ranking/risk_v1.py) |
| **Composite Final Score ($0 - 100$)** | $\text{Final Score} = 0.70 \times \text{Telemetry Risk} + 0.25 \times \text{Meter Impact} + 0.05 \times \text{Data Confidence}$ | [`app/ranking/risk_v1.py:score_single`](file:///Users/macbook/Desktop/CHALLENGE/app/ranking/risk_v1.py) |
| **Dynamic Weight Rebalancing** | When meter-read data is missing, weights rebalance to $\frac{0.70}{0.75} \times \text{Risk} + \frac{0.05}{0.75} \times \text{Confidence}$, preventing crashes or arbitrary zero-scoring. | [`app/ranking/risk_v1.py:score_single`](file:///Users/macbook/Desktop/CHALLENGE/app/ranking/risk_v1.py) |
| **Deterministic 4-Key Sort** | Tuple $\left(-\text{final\_score}, -\text{exposure\_meters}, -\text{total\_recent\_offline\_sec}, \text{gateway\_id}\right)$ ensuring 100% byte-for-byte reproducible rank order. | [`app/ranking/risk_v1.py:rank_gateways`](file:///Users/macbook/Desktop/CHALLENGE/app/ranking/risk_v1.py) |
| **Operational Reason (`reason`)** | High-signal, human-readable summary string strictly $\le 300$ characters describing the primary failure metric, flagged hours, and downstream customer impact for field technicians. | [`app/explanations/builder.py`](file:///Users/macbook/Desktop/CHALLENGE/app/explanations/builder.py) |

---

### 2.5 Architecture & Production Software Terms

| Term | Definition | Where It Is Handled |
| :--- | :--- | :--- |
| **Clean Architecture** | Architectural pattern separating system concerns into isolated layers: API $\rightarrow$ Services $\rightarrow$ Strategies $\rightarrow$ Domain $\rightarrow$ Repositories. | [`app/`](file:///Users/macbook/Desktop/CHALLENGE/app/) |
| **Strategy Pattern (`RankingStrategy`)** | Protocol defining a unified ranking contract (`name`, `score_single`, `rank_gateways`), allowing runtime switching between `risk_v1` and `baseline` models without modifying API routes. | [`app/domain/protocols.py`](file:///Users/macbook/Desktop/CHALLENGE/app/domain/protocols.py), [`app/ranking/base.py`](file:///Users/macbook/Desktop/CHALLENGE/app/ranking/base.py) |
| **Repository Pattern** | Decoupled data access objects (`TelemetryRepository`, `GatewayRepository`, `MeterReadRepository`) that encapsulate file loading, partition pruning, column casting, and ID normalisation. | [`app/repositories/`](file:///Users/macbook/Desktop/CHALLENGE/app/repositories/) |
| **OS File Concurrency Lock (`fcntl.flock`)** | Kernel-level exclusive advisory lock placed on `artifacts/.run.lock`. Serializes execution and returns HTTP `409 Conflict` on overlapping concurrent run requests. | [`app/services/run_service.py`](file:///Users/macbook/Desktop/CHALLENGE/app/services/run_service.py), [`tests/unit/test_run_locking.py`](file:///Users/macbook/Desktop/CHALLENGE/tests/unit/test_run_locking.py) |
| **Run Artifact Isolation** | Execution persistence where each API run writes exclusively to `artifacts/runs/<run_id>/predictions.csv` and `metadata.json`, leaving root `./predictions.csv` unmutated for CLI submissions. | [`app/output/writer.py`](file:///Users/macbook/Desktop/CHALLENGE/app/output/writer.py), [`app/services/run_service.py`](file:///Users/macbook/Desktop/CHALLENGE/app/services/run_service.py) |
| **Heartbeat & Orphaned Run Recovery** | Execution tracking with periodic heartbeat updates. If a worker process terminates abruptly (e.g. `SIGKILL`), stale locks exceeding 300s are transitioned to `ORPHANED`. | [`app/services/run_service.py`](file:///Users/macbook/Desktop/CHALLENGE/app/services/run_service.py), [`tests/regression/test_edge_cases.py`](file:///Users/macbook/Desktop/CHALLENGE/tests/regression/test_edge_cases.py) |
| **Atomic File Write** | File writing mechanism that writes to a temporary file (`.tmp_xxx`) on the same filesystem before performing an atomic rename (`os.replace`), preventing partial reads during crashes. | [`app/output/writer.py:write_csv_atomic`](file:///Users/macbook/Desktop/CHALLENGE/app/output/writer.py) |
| **FastAPI & Pydantic v2** | High-performance Python async web framework and data validation library generating automatic OpenAPI 3.1 schema documentation (`/docs`, `/redoc`). | [`app/api/app.py`](file:///Users/macbook/Desktop/CHALLENGE/app/api/app.py), [`app/domain/models.py`](file:///Users/macbook/Desktop/CHALLENGE/app/domain/models.py) |
| **Model Context Protocol (MCP)** | Standardised JSON-RPC protocol over Stdio exposing prioritisation and inspection tools directly to AI coding assistants and IDEs. | [`mcp_server.py`](file:///Users/macbook/Desktop/CHALLENGE/mcp_server.py) |

---

## 3. Step-by-Step Execution Lifecycle

The table below traces the exact sequence of events when running the pipeline or querying the API:

```
Step 1: Initiation
  │ CLI: `python main.py --data data --out predictions.csv` OR API: `POST /api/v1/runs`
  ▼
Step 2: Configuration & Concurrency Lock
  │ `AppConfig` loads settings from environment / defaults.
  │ `RunService` acquires non-blocking exclusive `fcntl.flock` on `artifacts/.run.lock`.
  ▼
Step 3: Repository Ingestion & Partition Pruning
  │ `GatewayRepository` loads `gateway_master.csv` & normalises 12-character hex IDs.
  │ `TelemetryRepository` prunes Parquet directory partitions (e.g. `month=2026-01`, `month=2026-02`).
  │ Loads hourly rows for `[cutoff - 28d, cutoff)` strictly before Monday 00:00:00 UTC.
  │ `MeterReadRepository` loads weekly success rates for `[cutoff - 28d, cutoff)`.
  ▼
Step 4: Quality Assessment Gate
  │ `DataQualityGate` verifies reference history (>= 14d) and detection history (>= 5d).
  │ Assigns `QualityAssessment` (flags active eligibility and confidence penalties).
  ▼
Step 5: Statistical Feature Extraction
  │ `FeatureBuilder` separates reference window `[cutoff - 28d, cutoff - 7d)` from detection window `[cutoff - 7d, cutoff)`.
  │ Calculates `Median`, `MAD`, and `Scale` with physical scale floors.
  │ Evaluates detection window hours, computes robust z-scores ($z \le 10.0\sigma$), and flags anomalies ($z > 3.0\sigma$).
  │ Computes persistence ratio $P$, severity $S$, and exponential recency $R$.
  │ Extracts meter-read degradation and sublinear exposure scale.
  ▼
Step 6: Scoring & Strategy Execution
  │ `RankingStrategy` (`RiskRanker`) computes Telemetry Risk, Meter Impact, and Data Confidence (0-100).
  │ Calculates weighted composite final score.
  ▼
Step 7: Deterministic Ranking & Operational Reasons
  │ Ranks all eligible gateways using the 4-key tuple.
  │ Selects top 15 gateways for the week.
  │ `ExplanationBuilder` generates operations-ready reason ($\le 300$ chars) for every gateway.
  ▼
Step 8: Output Delivery & Lock Release
  │ `ArtifactWriter` creates 120-row dataframe across all 8 scored weeks.
  │ Performs atomic write to `predictions.csv`.
  │ Releases `fcntl.flock` file lock.
  │ `validate_submission.py` validates output schema (0 errors).
```

---

## 4. Code Symbol Index

| Code Symbol | Type | Location | Purpose |
| :--- | :--- | :--- | :--- |
| `AppConfig` | Dataclass / Settings | [`app/config.py`](file:///Users/macbook/Desktop/CHALLENGE/app/config.py) | Central configuration parameters, weights, and directory paths. |
| `normalise_gateway_id` | Function | [`app/repositories/gateways.py`](file:///Users/macbook/Desktop/CHALLENGE/app/repositories/gateways.py) | Converts 12-char or colon-separated MAC/IDs into uppercase 12-hex strings. |
| `TelemetryRepository` | Class | [`app/repositories/telemetry.py`](file:///Users/macbook/Desktop/CHALLENGE/app/repositories/telemetry.py) | Loads partitioned Parquet telemetry with point-in-time filtering. |
| `compute_median_mad` | Function | [`app/features/builder.py`](file:///Users/macbook/Desktop/CHALLENGE/app/features/builder.py) | Computes non-parametric Median, MAD, and applied scale floor. |
| `FeatureBuilder` | Class | [`app/features/builder.py`](file:///Users/macbook/Desktop/CHALLENGE/app/features/builder.py) | Extracts decoupled telemetry and meter impact features. |
| `RankingStrategy` | Protocol | [`app/domain/protocols.py`](file:///Users/macbook/Desktop/CHALLENGE/app/domain/protocols.py) | Interface for swappable ranking algorithms. |
| `RiskRanker` | Class | [`app/ranking/risk_v1.py`](file:///Users/macbook/Desktop/CHALLENGE/app/ranking/risk_v1.py) | Multi-signal 0-100 scoring engine with exposure scaling. |
| `Baseline3SigmaRanker`| Class | [`app/ranking/baseline.py`](file:///Users/macbook/Desktop/CHALLENGE/app/ranking/baseline.py) | Baseline 3-sigma breach count ranker. |
| `ExplanationBuilder` | Class | [`app/explanations/builder.py`](file:///Users/macbook/Desktop/CHALLENGE/app/explanations/builder.py) | Generates $\le 300$-character explanations for ranked & unranked gateways. |
| `RankingService` | Class | [`app/services/ranking_service.py`](file:///Users/macbook/Desktop/CHALLENGE/app/services/ranking_service.py) | High-level service orchestrating weekly evaluation loops. |
| `GatewayService` | Class | [`app/services/gateway_service.py`](file:///Users/macbook/Desktop/CHALLENGE/app/services/gateway_service.py) | Single-gateway diagnostic and explanation service. |
| `RunService` | Class | [`app/services/run_service.py`](file:///Users/macbook/Desktop/CHALLENGE/app/services/run_service.py) | Manages run lifecycle, concurrency file locks, and heartbeats. |
| `ArtifactWriter` | Class | [`app/output/writer.py`](file:///Users/macbook/Desktop/CHALLENGE/app/output/writer.py) | Builds submission frames and executes atomic CSV writes. |
