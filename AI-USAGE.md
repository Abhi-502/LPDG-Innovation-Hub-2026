# AI Usage and Verification Log

> **LPDG Innovation Hub Selection Challenge 2026 — Unified AI Usage Statement**

---

## 1. AI Tools & Models Used
- **Assistant**: Antigravity AI Coding Assistant (powered by Google Gemini models).
- **Primary Use Cases**:
  - Code generation for modular components (`app/config.py`, `app/domain/`, `app/repositories/`, `app/features/`, `app/ranking/`, `app/services/`, `app/explanations/`, `app/output/`, `app/validation/`, `app/api/`, `mcp_server.py`).
  - Unit, integration, regression, and end-to-end test suite generation (`pytest` fixtures, synthetic parquet generators, concurrency locks).
  - OpenAPI schema and documentation structuring (`README.md`, `DECISIONS.md`, `docs/API.md`).

---

## 2. Methodology & Prompting Workflow
- **Domain-Constrained Decomposition**: Each subsystem was specified with strict interfaces, explicit mathematical bounds (0–100 normalization), half-open time intervals `[start, cutoff)`, and clean dependency injection.
- **Rigorous Multi-Stage Verification**:
  1. Automated testing of mathematical edge cases (zero-MAD scale floors, empty histories, tie-breaking stability).
  2. Concurrency stress testing (multi-threaded and multi-process file locking with `fcntl.flock`).
  3. Schema validation via official `validate_submission.py` checking the full 120-row output against all challenge requirements.
  4. Manual static code audit for temporal lookahead leakage and data integrity.

---

## 3. Concrete Errors Caught and Corrected

During development and static code audit, several critical issues were identified, analyzed, and corrected:

### Issue 1: Baseline Self-Contamination in Trailing Anomaly Windows
- **Discovered Problem**: In the initial 3-sigma baseline script, historical mean and standard deviation were computed over the full trailing 28 days `[cutoff - 28d, cutoff)`. When an active gateway experienced a sustained outage over the recent 7 days `[cutoff - 7d, cutoff)`, the failure data inflated the baseline mean and variance, artificially compressing the anomaly z-score and causing critical outages to under-rank.
- **Correction Applied**: Refactored `app/features/builder.py` to strictly decouple time windows into half-open intervals:
  - Reference window: `[cutoff - 28d, cutoff - 7d)` (21 days of baseline reference).
  - Detection window: `[cutoff - 7d, cutoff)` (7 days of recent detection).
- **Verification**: Verified in `tests/unit/test_boundaries_and_isolation.py`, proving an injected 168-hour complete outage in the detection window leaves reference statistics uncorrupted and achieves 100% persistence.

---

### Issue 2: Floating-Point Sort Non-Determinism on Identical Scores
- **Discovered Problem**: Sorting solely by `final_score` descending led to indeterminate ranking order when gateways had identical composite scores, making rankings sensitive to row order in the source files.
- **Correction Applied**: Implemented an explicit 4-tuple deterministic sort key in `app/ranking/risk_v1.py`:
  `(-final_score, -exposure_meters, -total_recent_offline_sec, gateway_id)`
  This guarantees 100% byte-for-byte reproducible rankings across environments and executions.
- **Verification**: Verified in `tests/unit/test_tie_breaking.py`.

---

### Issue 3: Partitioned Parquet Directory Loading Type Incompatibility
- **Discovered Problem**: The initial partition-pruning logic constructed a list of monthly directory `Path` objects (`[Path('telemetry/month=2026-01'), Path('telemetry/month=2026-02')]`) and passed them to `pd.read_parquet(read_target)`. In `pyarrow`, passing a list of directory paths raises `ArrowInvalid: Expected a file path or buffer, but found directory`.
- **Correction Applied**: Updated `TelemetryRepository.load_telemetry` to resolve target directory paths down to explicit `.parquet` file lists:
  `target_files.extend(sorted(d.glob("*.parquet")))`
  and validated column existence against parquet metadata before querying optional columns.
- **Verification**: Verified in `app/repositories/telemetry.py` and `tests/integration/test_pipeline_integration.py`.

---

### Issue 4: Zero-Scale False Alarms on Quiet Reference Baselines
- **Discovered Problem**: For gateways with constant 0 disconnections or 0 reboots throughout their reference history, MAD evaluated to 0. Using a naive tiny epsilon ($10^{-4}$) caused even a single momentary reconnection event ($x = 1$) to compute $z = 1 / 10^{-4} = 10,000\sigma$, triggering false maximum-severity anomaly scores.
- **Correction Applied**: Introduced domain-informed physical minimum scale floors in `AppConfig.metric_min_scales` (60.0s for offline duration, 1.0 for counts) in `app/features/builder.py`. A single benign reboot ($z = 1 / 1.0 = 1\sigma$) is ignored, while genuine multi-event surges properly breach the $3.0\sigma$ threshold.
- **Verification**: Verified in `tests/unit/test_features.py` and `tests/unit/test_robust_stats_and_weights.py`.

---

### Issue 5: Heterogeneous Meter-Read Reporting Week Alignment
- **Discovered Problem**: Initial meter-read feature extraction assumed all gateways reported on the single global `meter_df["week_start"].max()`. Gateways with reporting lags were falsely treated as having missing telemetry data.
- **Correction Applied**: Refactored `FeatureBuilder.extract_meter_impact_features` to locate each gateway's individual latest reporting record using `groupby("gateway_id")["week_start"].idxmax()`.
- **Verification**: Verified in `app/features/builder.py` and `tests/unit/test_robust_stats_and_weights.py`.
