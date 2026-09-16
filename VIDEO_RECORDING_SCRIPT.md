# Video Presentation Script & Screen Recording Walkthrough

> **LPDG Innovation Hub Selection Challenge 2026**  
> **Target Duration**: 6 to 8 minutes  
> **Audience**: Evaluation Panel & Operations Manager  
> **Tone**: Confident, technically rigorous, operations-aware, and disciplined.

---

## 1. Video Structure & Timing Plan

```
┌─────────────────┬───────────────────────────────────────────────┬──────────────┐
│ Section         │ What to Show on Screen                        │ Time         │
├─────────────────┼───────────────────────────────────────────────┼──────────────┤
│ 1. Introduction │ Terminal / Slide: Problem Framing & Economics │ 0:00 - 1:00  │
│ 2. Part 1 Run   │ Terminal: `make run` & `make validate`        │ 1:00 - 2:30  │
│ 3. Key Decisions│ Code & Formula: Isolation & Median/MAD Floors │ 2:30 - 4:00  │
│ 4. Part 2 Demo  │ Browser: FastAPI Swagger UI (`/docs`)         │ 4:00 - 5:30  │
│ 5. Test Suite   │ Terminal: `pytest -v` (48 Passing Tests)      │ 5:30 - 6:45  │
│ 6. Roadmap      │ DECISIONS.md: "What It Cannot Do" & Next Steps│ 6:45 - 7:30  │
└─────────────────┴───────────────────────────────────────────────┴──────────────┘
```

---

## 2. Step-by-Step Speaking Script & Screen Actions

---

### Section 1: Problem Framing & Operational Economics (0:00 – 1:00)

**What to show**: Code editor with project title or clean terminal in `/Users/macbook/Desktop/CHALLENGE`.

**What to say**:
> "Hello, my name is [Your Name]. Today I am presenting my solution for the LPDG Innovation Hub 2026 Selection Challenge.
>
> In our IoT smart meter network, 320 gateways relay readings for over 40 to 900 meters each. When gateways fail silently, readings stop, resulting in estimated billing errors and dissatisfied customers.
>
> Operationally, the field team has a hard capacity limit of **15 visits per week**. The economic stakes are high:
> - Sending a technician to a healthy gateway wastes **€380**.
> - Leaving a broken gateway unaddressed costs **€600 every week** it stays broken.
>
> For Part 1, I built a deterministic, point-in-time multi-signal scoring engine. For Part 2, I selected **Software Development**, productising this engine into a modular, concurrency-safe FastAPI service with pluggable ranking strategies and comprehensive diagnostics."

---

### Section 2: Part 1 Execution & Submission Validation (1:00 – 2:30)

**What to show**: Terminal window. Run `make run` and `make validate`.

**Command to run**:
```bash
make run
make validate
head -n 5 predictions.csv
```

**What to say**:
> "Let's first execute the Part 1 pipeline. With one single command — `make run` or `python main.py` — the pipeline processes the partitioned Parquet telemetry, gateway master records, and weekly meter-read success logs.
>
> Notice how cleanly it scores all 8 target Mondays strictly up to Monday 00:00:00 UTC.
>
> Running `make validate` executes the official innovation hub validator:
> - It confirms **120 rows** — exactly 15 unique gateways for each of the 8 scored weeks.
> - All 5 required columns are present with valid scores and normalized 12-hex IDs.
> - Every gateway includes an informative, operations-ready reason strictly under 300 characters."

---

### Section 3: Engineering Judgement & Key Decisions (2:30 – 4:00)

**What to show**: Open [`DECISIONS.md`](file:///Users/macbook/Desktop/CHALLENGE/DECISIONS.md) or [`app/features/builder.py`](file:///Users/macbook/Desktop/CHALLENGE/app/features/builder.py).

**What to say**:
> "I want to highlight three critical engineering decisions I defended in `DECISIONS.md`:
>
> 1. **Baseline Window Isolation**:
>    The standard baseline script computed statistics over trailing 28 days and evaluated the last 7 days of that exact same window. When a gateway experienced a sustained 7-day outage, the failure data inflated its own baseline mean and variance, artificially compressing its anomaly z-score. I decoupled this into a **21-day historical reference window** `[cutoff - 28d, cutoff - 7d)` and a **7-day detection window** `[cutoff - 7d, cutoff)`. Recent failures cannot inflate their baseline.
>
> 2. **Robust Statistics (Median / MAD) with Physical Scale Floors**:
>    Mean and standard deviation break down under historical maintenance spikes. I used Median and Median Absolute Deviation with a 1.4826 normal scale factor. Crucially, I added physical scale floors (60 seconds for offline duration, 1.0 for event counts). On quiet gateways with zero past reboots ($\text{MAD}=0$), this prevents a single benign reboot from triggering an artificial $10,000\sigma$ false alarm.
>
> 3. **Sublinear Exposure Scaling & Deterministic Tie-Breaks**:
>    Telemetry anomalies indicate instability, but customer impact depends on affected meters. I scaled meter impact by $\ln(1 + \text{meters}) / \ln(1 + 500)$ so high-meter sites are prioritized without smaller regional sites being starved. All rankings use a deterministic 4-key sort: `(-final_score, -exposure_meters, -total_recent_offline_sec, gateway_id)` guaranteeing 100% reproducible ordering."

---

### Section 4: Part 2 Software Development & API Demo (4:00 – 5:30)

**What to show**: Browser at `http://localhost:8000/docs` (Swagger UI).

**Commands in terminal before opening browser**:
```bash
make api
```

**Actions in Swagger UI**:
1. Open `GET /health` $\rightarrow$ Click **Try it out** $\rightarrow$ **Execute** (Show `status: healthy`, `data_dir_ready: true`).
2. Open `GET /api/v1/weeks/{week_start}/predictions` $\rightarrow$ Enter `2026-03-23` $\rightarrow$ **Execute** (Show 15 ranked gateways with ranks 1..15, scores, and reasons).
3. Open `GET /api/v1/gateways/{gateway_id}` $\rightarrow$ Enter `0202CB0A6B1F` $\rightarrow$ **Execute** (Show full diagnostic breakdown: status, rank, telemetry features, meter features, quality assessment).
4. Open `POST /api/v1/runs` $\rightarrow$ **Execute** (Show isolated run created under `artifacts/runs/<run_id>/`).

**What to say**:
> "Now moving to Part 2 — Software Development. The entire decision engine is exposed as a modular FastAPI service with clean architectural layering.
>
> - `GET /health` checks system health and verifies access to underlying parquet partitions.
> - `GET /api/v1/weeks/{date}/predictions` returns the weekly 15 prioritised visits with full operational reasons.
> - `GET /api/v1/gateways/{id}` provides deep diagnostic explanations for ranked, unranked, and ineligible gateways. Field teams and operations managers can inspect why any gateway is where it is.
> - `POST /api/v1/runs` enables asynchronous/synchronous execution with **OS-level concurrency file locking (`fcntl.flock`)**. Concurrent run attempts return `409 Conflict`, and API runs write to isolated folders under `artifacts/runs/` without modifying the root `predictions.csv`.
> - Furthermore, ranking strategies implement a pluggable `RankingStrategy` protocol, allowing seamless switching between `risk_v1` and `baseline` models without altering API routes."

---

### Section 5: Automated Testing & Error Correction (5:30 – 6:45)

**What to show**: Terminal running `pytest -v`.

**Command to run**:
```bash
pytest -v
```

**What to say**:
> "The codebase is backed by a comprehensive suite of **48 automated tests** covering unit, integration, regression, and end-to-end flows.
>
> Notice the specialized test cases:
> - `test_recent_failure_does_not_contaminate_reference_baseline` verifies zero leakage.
> - `test_concurrency_lock_prevents_overlapping_runs` verifies atomic file locks.
> - `test_orphaned_run_heartbeat_recovery` verifies automatic recovery from simulated process crashes.
> - `test_deterministic_tie_breaks` verifies stable ordering.
>
> In `AI-USAGE.md`, I also documented 5 concrete bugs caught during development — including PyArrow directory-level loading errors, floating-point tie-break instability, and zero-MAD false alarm singularities."

---

### Section 6: What It Cannot Do & Two-Week Roadmap (6:45 – 7:30)

**What to show**: [`DECISIONS.md`](file:///Users/macbook/Desktop/CHALLENGE/DECISIONS.md) section *"What It Cannot Do"*.

**What to say**:
> "Finally, let's address what this system cannot currently do and what another two weeks would buy:
>
> 1. **Spatial Routing Optimization**:
>    Currently, the engine selects the 15 highest-risk individual gateways, but does not consider travel distance between sites. With another week, I would integrate GPS coordinates from `gateway_master.csv` into a Vehicle Routing Problem (VRP) solver to group technician visits into geographically optimal clusters.
>
> 2. **Closed-Loop Feedback from Field Visits**:
>    In week two, I would ingest historical technician findings from `field_visits.csv` into a Bayesian reinforcement model to penalize recurring false alarms and boost confidence on chronic hardware degradation.
>
> In summary, this repository delivers a deterministic, submission-safe decision engine and a robust, production-ready software development architecture. Thank you for your time!"

---

## 3. Preparation Checklist Before Recording

1. **Clean Terminal State**:
   ```bash
   cd /Users/macbook/Desktop/CHALLENGE
   make clean
   ```
2. **Pre-check Services**:
   - Verify `python3 validate_submission.py predictions.csv` outputs `predictions.csv: OK`.
   - Verify `pytest -v` shows `48 passed`.
   - Start the API server in a separate terminal: `python3 main.py --serve`.
   - Open browser tab at `http://localhost:8000/docs`.
3. **Screen Setup**:
   - Position terminal on the left and browser / code editor on the right (or switch cleanly via full screen).
   - Set terminal font size to 16pt+ for high readability.
