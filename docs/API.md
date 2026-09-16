# Gateway Prioritisation API Reference (Part 2)

LPDG Innovation Hub Selection Challenge 2026 — Part 2 Software Development API.

---

## 1. Overview

The Gateway Prioritisation API exposes the deterministic Part 1 decision engine as a high-performance, modular REST service built on **FastAPI**.

- **Base URL**: `http://localhost:8000`
- **Interactive Documentation**: `http://localhost:8000/docs` (Swagger UI) or `http://localhost:8000/redoc` (ReDoc)
- **OpenAPI JSON**: `http://localhost:8000/openapi.json`

---

## 2. API Endpoints

### 2.1 System Health & Readiness

```http
GET /health
```

Checks system health and verifies access to the underlying parquet/CSV data directory.

#### Response (200 OK)
```json
{
  "status": "healthy",
  "timestamp": "2026-03-23T10:00:00.000000+00:00",
  "version": "0.2.0",
  "environment": "development",
  "data_dir_ready": true,
  "ranking_method": "risk_v1"
}
```

#### Curl Example
```bash
curl -X GET "http://localhost:8000/health"
```

---

### 2.2 Weekly Gateway Predictions

```http
GET /api/v1/weeks/{week_start}/predictions
```

Retrieves the top 15 ranked gateways for a given scored Monday decision cutoff.

#### Path Parameters
| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `week_start` | string (ISO Date) | Yes | Monday cutoff date in `YYYY-MM-DD` format (e.g. `2026-03-23`). |

#### Query Parameters
| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `run_id` | string | No | `null` | Optional execution run ID to resolve artifacts from. If omitted, returns latest successful default run. |
| `ranking_method` | string | No | `risk_v1` | Optional ranking algorithm strategy (`risk_v1` or `baseline`). |

#### Response (200 OK)
```json
{
  "week_start": "2026-03-23",
  "ranking_method": "risk_v1",
  "run_id": "run_20260323_120000_a1b2c3",
  "count": 15,
  "predictions": [
    {
      "rank": 1,
      "gateway_id": "0202CB0A6B1F",
      "score": 88.4215,
      "reason": "High priority (Rank 1): 24 abnormal offline duration hour(s) in last 7 days vs 21-day baseline. Meter reads fell to 78% across 450 expected meters.",
      "ranking_method": "risk_v1"
    },
    {
      "rank": 2,
      "gateway_id": "0202CB0A703A",
      "score": 76.1904,
      "reason": "High priority (Rank 2): 18 abnormal disconnections hour(s) in last 7 days vs 21-day baseline. Meter reads at 91% across 320 expected meters.",
      "ranking_method": "risk_v1"
    }
  ]
}
```

#### Status Codes
- `200 OK`: Successful response with 15 ranked gateways.
- `400 Bad Request`: Malformed date format or invalid parameters.
- `404 Not Found`: Week date outside supported scoring window (`2026-02-02` to `2026-03-23`) or specified `run_id` not found.
- `503 Service Unavailable`: Underlying telemetry or master data is inaccessible.

#### Curl Example
```bash
curl -X GET "http://localhost:8000/api/v1/weeks/2026-03-23/predictions"
```

---

### 2.3 Single Gateway Explanation & Evaluation

```http
GET /api/v1/weeks/{week_start}/gateways/{gateway_id}
```

Provides diagnostic explainability and detailed feature breakdowns for any known gateway.

#### Gateway Status Semantics
1. **Ranked in Top 15 (`RANKED_TOP_15`)**: Returns `200 OK` with priority rank (1..15), score, and operational reason.
2. **Eligible but Unranked (`ELIGIBLE_UNRANKED`)**: Returns `200 OK` with its overall rank (> 15), score, telemetry metrics, and explanation of why it was below quota.
3. **Ineligible (`INELIGIBLE`)**: Returns `200 OK` with `score: null`, `rank: null`, and explicit disqualification reason (e.g. decommissioned or insufficient history).
4. **Unknown Gateway**: Returns `404 Not Found` if `gateway_id` is absent from `gateway_master.csv`.

#### Path Parameters
| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `week_start` | string (ISO Date) | Yes | Scored Monday cutoff date (`YYYY-MM-DD`). |
| `gateway_id` | string (Hex) | Yes | Gateway identifier in 12-char hex (`0202CB0A6B1F`) or colon format (`02:02:CB:0A:6B:1F`). |

#### Response (200 OK — Ranked Gateway)
```json
{
  "gateway_id": "0202CB0A6B1F",
  "week_start": "2026-03-23",
  "status": "RANKED_TOP_15",
  "rank": 1,
  "score": 88.4215,
  "ranking_method": "risk_v1",
  "reason": "High priority (Rank 1): 24 abnormal offline duration hour(s) in last 7 days vs 21-day baseline. Meter reads fell to 78% across 450 expected meters.",
  "is_eligible": true,
  "details": {
    "tenant": "tenant_nord",
    "region": "Bayern",
    "site_type": "Schaltschrank",
    "hw_model": "GW-2100",
    "installed_on": "2023-01-15",
    "decommissioned_on": null,
    "n_meters_installed": 450,
    "score_breakdown": {
      "final_score": 88.4215,
      "telemetry_risk": 92.15,
      "meter_impact": 81.33,
      "data_confidence": 100.0
    },
    "telemetry_features": {
      "flagged_hours": 24,
      "total_detection_hours": 168,
      "persistence_ratio": 0.1429,
      "avg_anomaly_severity": 4.821,
      "worst_metric": "offline_duration_sec",
      "total_recent_offline_sec": 34200.0
    },
    "meter_features": {
      "meters_expected": 450,
      "meters_read": 351,
      "read_success_ratio": 0.78,
      "exposure_meters": 450,
      "has_meter_data": true
    },
    "quality": {
      "is_full_quality": true,
      "reference_days": 21,
      "detection_days": 7
    }
  }
}
```

#### Response (200 OK — Ineligible Gateway)
```json
{
  "gateway_id": "0202CB0A9999",
  "week_start": "2026-03-23",
  "status": "INELIGIBLE",
  "rank": null,
  "score": null,
  "ranking_method": "risk_v1",
  "reason": "Ineligible: Gateway decommissioned on 2026-01-10, prior to target date 2026-03-23.",
  "is_eligible": false,
  "details": {
    "tenant": "tenant_nord",
    "region": "Bayern",
    "site_type": "Schaltschrank",
    "hw_model": "GW-2100",
    "installed_on": "2022-05-01",
    "decommissioned_on": "2026-01-10",
    "n_meters_installed": 50,
    "reference_days": 0,
    "detection_days": 0,
    "rejection_reason": "Not active"
  }
}
```

#### Curl Example
```bash
curl -X GET "http://localhost:8000/api/v1/weeks/2026-03-23/gateways/0202CB0A6B1F"
```

---

### 2.4 Trigger Prioritisation Execution Run

```http
POST /api/v1/runs
```

Executes a synchronous prioritisation run across requested weeks.

#### Concurrency & Locking
- Uses an OS-level file lock (`fcntl.flock`) on `artifacts/.run.lock`.
- If a run is already in progress, immediately returns **`409 Conflict`**.
- Persists isolated artifacts under `artifacts/runs/<run_id>/predictions.csv` and `artifacts/runs/<run_id>/metadata.json`.

#### Request Body
```json
{
  "weeks": ["2026-03-23"],
  "ranking_method": "risk_v1"
}
```
*(If `weeks` is omitted or null, all 8 scored weeks are processed).*

#### Response (201 Created)
```json
{
  "run_id": "run_20260323_120000_a1b2c3",
  "status": "SUCCEEDED",
  "ranking_method": "risk_v1",
  "requested_weeks": [
    "2026-03-23"
  ],
  "started_at": "2026-03-23T12:00:00.123456+00:00",
  "heartbeat_at": "2026-03-23T12:00:02.345678+00:00",
  "completed_at": "2026-03-23T12:00:02.500000+00:00",
  "error_message": null,
  "artifact_paths": {
    "predictions_csv": "/app/artifacts/runs/run_20260323_120000_a1b2c3/predictions.csv",
    "metadata_json": "/app/artifacts/runs/run_20260323_120000_a1b2c3/metadata.json"
  }
}
```

#### Curl Example
```bash
curl -X POST "http://localhost:8000/api/v1/runs" \
     -H "Content-Type: application/json" \
     -d '{"weeks": ["2026-03-23"], "ranking_method": "risk_v1"}'
```

---

### 2.5 Get Execution Run Status

```http
GET /api/v1/runs/{run_id}
```

Retrieves metadata and lifecycle status (`CREATED`, `RUNNING`, `SUCCEEDED`, `FAILED`, `ORPHANED`) for a run.

#### Path Parameters
| Parameter | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `run_id` | string | Yes | Unique run identifier. |

#### Response (200 OK)
```json
{
  "run_id": "run_20260323_120000_a1b2c3",
  "status": "SUCCEEDED",
  "ranking_method": "risk_v1",
  "requested_weeks": ["2026-03-23"],
  "started_at": "2026-03-23T12:00:00.123456+00:00",
  "heartbeat_at": "2026-03-23T12:00:02.345678+00:00",
  "completed_at": "2026-03-23T12:00:02.500000+00:00",
  "error_message": null,
  "artifact_paths": {
    "predictions_csv": "/app/artifacts/runs/run_20260323_120000_a1b2c3/predictions.csv",
    "metadata_json": "/app/artifacts/runs/run_20260323_120000_a1b2c3/metadata.json"
  }
}
```

#### Curl Example
```bash
curl -X GET "http://localhost:8000/api/v1/runs/run_20260323_120000_a1b2c3"
```

---

## 3. Error Contract Summary

| Status Code | Reason | Example Response |
| :--- | :--- | :--- |
| `400 Bad Request` | Invalid date or parameter format | `{"detail": "Invalid date format '2026-13-45'. Expected YYYY-MM-DD.", "status_code": 400}` |
| `404 Not Found` | Unknown gateway, run, or week | `{"detail": "Gateway '020000000099' was not found in gateway master records.", "status_code": 404}` |
| `409 Conflict` | Concurrent run in progress | `{"detail": "Another prioritisation run is currently in progress.", "status_code": 409}` |
| `422 Unprocessable`| Pydantic schema validation error | Fast-API standard validation error payload |
| `503 Unavailable` | Underlying dataset missing | `{"detail": "Gateway master file not found at ./data/gateway_master.csv", "status_code": 503}` |
| `500 Server Error` | Unexpected unhandled exception | `{"detail": "Internal server error occurred.", "status_code": 500}` |
