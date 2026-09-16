"""Synthetic data generation utilities for test suites."""

from __future__ import annotations

import datetime as dt
import pathlib
import pandas as pd


def generate_mock_environment(
    data_dir: pathlib.Path,
    num_gateways: int = 25,
    start_date: str = "2026-01-01",
    end_date: str = "2026-03-30",
) -> list[str]:
    """Generate mock gateway_master, meter_read_success, and partitioned telemetry."""
    data_dir.mkdir(parents=True, exist_ok=True)
    telemetry_dir = data_dir / "telemetry"
    telemetry_dir.mkdir(parents=True, exist_ok=True)

    gateways = [f"0200000000{i:02X}" for i in range(1, num_gateways + 1)]

    # 1. Gateway Master CSV
    gm_rows = []
    for i, gw in enumerate(gateways, start=1):
        # Make one gateway decommissioned and one future installed for testing ineligible cases
        installed = "2023-01-01"
        decom = ""
        if i == num_gateways:
            decom = "2026-01-10"  # Decommissioned early
        elif i == num_gateways - 1:
            installed = "2026-04-01"  # Installed in future

        gm_rows.append(
            {
                "gateway_id": gw,
                "tenant": f"tenant_{i % 3}",
                "site_type": "Schaltschrank",
                "region": "Bayern" if i % 2 == 0 else "Berlin",
                "hw_model": "GW-2100",
                "installed_on": installed,
                "decommissioned_on": decom,
                "n_meters_installed": 100 + i * 10,
            }
        )
    pd.DataFrame(gm_rows).to_csv(data_dir / "gateway_master.csv", index=False)

    # 2. Meter Read Success CSV
    mrs_rows = []
    for w in range(14):
        week_date = dt.date(2025, 12, 1) + dt.timedelta(weeks=w)
        for i, gw in enumerate(gateways):
            exp = 100 + (i + 1) * 10
            # Inject drop for gateway 1 and 2
            read = exp - 30 if i < 2 and w >= 8 else exp - 2
            mrs_rows.append(
                {
                    "week_start": week_date.isoformat(),
                    "gateway_id": gw,
                    "meters_expected": exp,
                    "meters_read": max(0, read),
                }
            )
    pd.DataFrame(mrs_rows).to_csv(data_dir / "meter_read_success.csv", index=False)

    # 3. Telemetry Partitioned Parquet
    timestamps = pd.date_range(start=f"{start_date} 00:00:00", end=f"{end_date} 00:00:00", freq="1h", tz="UTC")
    tel_rows = []
    for i, gw in enumerate(gateways):
        for ts in timestamps:
            # Inject high offline anomalies for gateway 1 and 2 in detection window
            is_recent_spike = (i < 2) and (ts >= pd.Timestamp("2026-03-16", tz="UTC"))
            tel_rows.append(
                {
                    "gateway_id": gw,
                    "ts_utc": ts.strftime("%Y-%m-%d %H:%M:%S%z"),
                    "offline_duration_sec": 1800.0 if is_recent_spike else 5.0,
                    "disconnection_cnt": 3 if is_recent_spike else 0,
                    "reboot_cnt": 1 if is_recent_spike else 0,
                    "reboot_importance": 0.5 if is_recent_spike else 0.0,
                    "no_conn_importance": 0.5 if is_recent_spike else 0.0,
                }
            )
    tel_df = pd.DataFrame(tel_rows)

    months = ["2026-01", "2026-02", "2026-03"]
    for m in months:
        m_dir = telemetry_dir / f"month={m}"
        m_dir.mkdir(parents=True, exist_ok=True)
        m_part = tel_df[tel_df["ts_utc"].str.startswith(m)]
        if not m_part.empty:
            m_part.to_parquet(m_dir / "part-0.parquet", index=False)

    return gateways
