# Architectural Decision Records (ADRs) & Engineering Defense

> **LPDG Innovation Hub Selection Challenge 2026 — Unified Part 1 (Prioritisation Engine) & Part 2 (Software Development Production Architecture)**

---

## 1. Primary Architectural Decisions

### Decision 1: Deterministic Multi-Signal Scoring Engine (No ML in Part 1)
* **Choice**: Implement a deterministic, point-in-time, multi-signal scoring pipeline rather than a black-box machine learning classifier or regression model.
* **Rationale**:
  1. Part 1 evaluates engineering discipline, temporal correctness, zero lookahead leakage, determinism, and explainability.
  2. Telemetry failure ground-truth labels are not provided as a direct supervised classification target. Fitting complex models on self-supervised proxy targets introduces severe risk of label leakage, overfitting to synthetic seasonal artifacts, and opaque failure modes during unseen live evaluation.
  3. Clear mathematical formulation guarantees exact reproducibility and explainability for operations managers and field technicians.
* **Alternatives Considered & Rejected**:
  - Supervised GBDT (LightGBM/XGBoost) or anomaly autoencoders: Rejected due to operational complexity, risk of temporal leakage across weekly horizons, lack of ground truth labels, and reduced explainability for field teams.

---

### Decision 2: Retain UTC Decision Clock with Decoupled Reference (21d) and Detection (7d) Windows
* **Choice**: Standardise decision cutoffs to Monday 00:00:00 UTC, while strictly isolating the 21-day historical reference baseline `[cutoff - 28d, cutoff - 7d)` from the 7-day detection window `[cutoff - 7d, cutoff)`.
* **Rationale**:
  1. The brief's note ("All times IST") governs the challenge submission deadlines, not the synthetic fleet data clock. In the Data Dictionary, `ts_utc` is recorded in UTC. Retaining UTC aligns directly with the benchmark baseline while keeping timezones cleanly parameterised in `AppConfig`.
  2. The supplied baseline calculated mean/std on the entire trailing 28 days and flagged anomalies in the final 7 days of that same window. Under sustained failure (e.g., 7 consecutive days offline), a broken gateway heavily inflates its own baseline mean and variance, artificially compressing its anomaly z-score. Separating the reference window completely eliminates self-contamination.
* **Alternatives Considered & Rejected**:
  - Overlapping 28-day baseline: Rejected because prolonged outages dilute anomaly detection sensitivity.
  - Silently forcing Europe/Berlin local midnight: Rejected to maintain absolute temporal alignment with UTC parquet partitions.

---

### Decision 3: Robust Statistics (Median / MAD) with Physical Scale Floors
* **Choice**: Calculate gateway-relative baselines using non-parametric robust estimators (Median and Median Absolute Deviation with a 1.4826 normal consistency factor), combined with domain-informed physical minimum scale floors (`PipelineConfig.metric_min_scales`), capping individual hour anomaly severities at 10.0$\sigma$.
* **Rationale**:
  1. Classical mean and standard deviation are fragile against historical outliers and multi-hour maintenance spikes. Median and MAD provide high breakdown points (50%) and resist historical contamination.
  2. Gateways with constant zero disconnections or reboots yield zero MAD. Using arbitrary tiny epsilons ($10^{-4}$) causes single benign events ($x = 1$) to compute $z = 10,000\sigma$. Physical scale floors (e.g., 60.0s for offline duration, 1.0 for counts) prevent false-positive explosions.
  3. Importance fields (`reboot_importance`, `no_conn_importance`) correlate with raw counters; applying them as bounded multiplicative boosters ($\le 1.15\times$) avoids double-counting underlying failure modes.
* **Alternatives Considered & Rejected**:
  - Parametric Gaussian 3-Sigma without scale bounds: Vulnerable to historical outlier distortion and zero-variance singularities.
  - Blindly summing raw counter values with importance scores: Double-counts identical failure events.

---

### Decision 4: Composite 0–100 Scoring with Sublinear Exposure Scaling & Dynamic Rebalancing
* **Choice**: Combine Telemetry Risk (0.70 weight), Downstream Meter-Read Impact (0.25 weight), and Data Confidence (0.05 weight) on an explicit 0–100 normalized scale, sublinearly scaled by meter fleet exposure ($\ln(1 + \text{meters})$), with dynamic weight rebalancing when meter data is missing.
* **Rationale**:
  1. Telemetry anomalies indicate technical instability, but downstream customer and billing impact depends on whether meter readings actually failed.
  2. A failure affecting 500 meters incurs significantly higher business risk than an identical failure on a gateway serving 5 meters. Sublinear logarithmic scaling prevents mega-sites from permanently starving smaller sites while ensuring exposure breaks ties effectively.
  3. When meter-read data is missing, the engine gracefully renormalizes the telemetry and confidence weights without crashing or producing arbitrary penalties.
* **Alternatives Considered & Rejected**:
  - Prioritising purely on telemetry anomaly count without regard to meter count or customer impact.
  - Linear exposure scaling (which would allow massive sites to dominate all 15 weekly slots indefinitely).

---

### Decision 5: Part 2 Specialization Track — Software Development
* **Choice**: Select **Software Development (Area B)** as the Part 2 focus area, delivering a production-grade FastAPI REST service, extensible `RankingStrategy` protocol, OS-level concurrency locking (`fcntl.flock`), diagnostic endpoints, isolated run artifacts, and an Stdio MCP server interface.
* **Rationale**:
  1. Productising the deterministic Part 1 decision engine into a modular, clean-architecture service delivers immediate operational utility to both technical systems and business operators.
  2. Separation of concerns: API routing, domain models, services, strategies, repositories, explanations, and quality validation are completely decoupled.
  3. Strategy pattern enables zero-friction swapping of ranking algorithms (`risk_v1`, `baseline`) without touching API routes.
  4. Concurrency protection via non-blocking OS locks prevents race conditions and resource exhaustion, returning clean `409 Conflict` on overlapping runs while isolating run artifacts under `artifacts/runs/<run_id>/`.
* **Alternatives Considered & Rejected**:
  - Data Engineering / ML / DevOps standalone: While all infrastructure best practices (Docker, compose, Makefile, type hints, CI-ready tests) are incorporated, Software Development provides the highest architectural clarity, extensibility, and interface versatility.

---

## 2. What the System Cannot Do & Two-Week Roadmap

### Where the System Currently Falls Over
1. **Geographic Clustering & Route Optimization**:
   The current ranker produces the optimal 15 individual gateways based on risk, severity, and customer impact, but does not consider physical travel time or cluster proximity between sites. In reality, a technician sent to Berlin could visit two adjacent lower-risk gateways at near-zero marginal cost rather than driving across regions.
2. **Online Streaming Ingestion & Real-Time Event Processing**:
   The pipeline executes weekly batch runs over partitioned Parquet and CSV files. It does not maintain a continuous in-memory state or listen to real-time MQTT/Kafka telemetry streams.
3. **Feedback Loop from Historical Field Visits**:
   Past technician visit logs (`field_visits.csv`) are currently used for diagnostic inspection, but the engine does not automatically adjust risk weights based on historical technician findings (e.g. false alarms vs actual hardware replacements).
4. **Multi-Tenant Access Control & Authentication**:
   The REST API and MCP server currently operate within a trusted internal network boundary without OAuth2/JWT role-based access control (RBAC).

### What Another Two Weeks Would Fix
* **Week 1 — Spatial Clustering & Route Planning**:
  Integrate gateway GPS coordinates from `gateway_master.csv` with a Traveling Salesperson / Vehicle Routing Problem (VRP) solver (e.g. OR-Tools) to output geographically clustered weekly technician routes, maximizing visited meter coverage while minimizing travel time.
* **Week 2 — Closed-Loop Reinforcement & Authentication**:
  - Ingest `field_visits.csv` findings into a calibrated Bayesian feedback loop, suppressing recurring false-positive sensor glitches and boosting precision on chronic failure modes.
  - Implement JWT/OAuth2 bearer authentication, rate limiting, and Prometheus metric exporters (`/metrics`) for enterprise production observability.
