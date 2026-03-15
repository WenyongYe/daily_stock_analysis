#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回填最近一年的官方利率期限结构到 macro_rates.db。

默认：回填最近 365 天（按完整曲线可用交易日）
数据源：FRED 主源，Treasury 同日对账
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "data" / "macro_rates.db"

FRED_SERIES = {
    "3M": "DGS3MO",
    "2Y": "DGS2",
    "5Y": "DGS5",
    "10Y": "DGS10",
    "30Y": "DGS30",
}

TREASURY_MAP = {
    "3 Mo": "3M",
    "2 Yr": "2Y",
    "5 Yr": "5Y",
    "10 Yr": "10Y",
    "30 Yr": "30Y",
}


def http_get_text(url: str, timeout: float = 15.0, retries: int = 2) -> str | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (OpenClaw backfill_rates_history)",
        "Accept": "text/csv,text/plain;q=0.9,*/*;q=0.8",
    }
    for i in range(retries + 1):
        try:
            r = requests.get(url, timeout=timeout, headers=headers)
            if r.status_code == 200:
                return r.text
        except Exception:
            pass
    return None


def fetch_fred_series(series_id: str) -> dict[str, float]:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    body = http_get_text(url)
    if not body:
        return {}

    rd = csv.DictReader(io.StringIO(body))
    date_col = "DATE" if "DATE" in (rd.fieldnames or []) else "observation_date"
    out: dict[str, float] = {}
    for row in rd:
        d = (row.get(date_col) or "").strip()
        v = (row.get(series_id) or "").strip()
        if not d or not v or v == ".":
            continue
        try:
            out[d] = round(float(v), 3)
        except ValueError:
            continue
    return out


def fetch_treasury_history(start_year: int, end_year: int) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for year in range(start_year, end_year + 1):
        url = (
            "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
            f"daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve&"
            f"field_tdr_date_value={year}&page&_format=csv"
        )
        body = http_get_text(url)
        if not body or not body.strip():
            continue

        rd = csv.DictReader(io.StringIO(body))
        for row in rd:
            raw_date = (row.get("Date") or row.get("DATE") or "").strip()
            if not raw_date:
                continue
            try:
                # treasury uses mm/dd/YYYY
                d = datetime.strptime(raw_date, "%m/%d/%Y").date().isoformat()
            except ValueError:
                continue

            rates: dict[str, float] = {}
            for col, tenor in TREASURY_MAP.items():
                vv = (row.get(col) or "").strip()
                if not vv:
                    continue
                try:
                    rates[tenor] = round(float(vv), 3)
                except ValueError:
                    continue
            if rates:
                out[d] = rates
    return out


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS yield_curve_daily (
            observation_date TEXT PRIMARY KEY,
            source_primary TEXT NOT NULL,
            source_secondary TEXT,
            quality TEXT,
            asof_utc TEXT,
            stale_days INTEGER,
            y3m REAL,
            y2y REAL,
            y5y REAL,
            y10y REAL,
            y30y REAL,
            spread_2y10y_bp REAL,
            spread_3m10y_bp REAL,
            curve_shape TEXT,
            validation_json TEXT,
            raw_json TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def curve_shape(spread_3m10y_bp: float | None) -> str:
    if spread_3m10y_bp is None:
        return "未知"
    if spread_3m10y_bp < -50:
        return "🔴 深度倒挂"
    if spread_3m10y_bp < 0:
        return "🟠 倒挂"
    if spread_3m10y_bp < 30:
        return "🟡 平坦"
    if spread_3m10y_bp < 100:
        return "🟢 正常"
    return "🔵 陡峭"


def upsert_row(conn: sqlite3.Connection, payload: dict) -> None:
    r = payload["rates"]
    conn.execute(
        """
        INSERT INTO yield_curve_daily (
            observation_date, source_primary, source_secondary, quality, asof_utc,
            stale_days, y3m, y2y, y5y, y10y, y30y,
            spread_2y10y_bp, spread_3m10y_bp, curve_shape,
            validation_json, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(observation_date) DO UPDATE SET
            source_primary=excluded.source_primary,
            source_secondary=excluded.source_secondary,
            quality=excluded.quality,
            asof_utc=excluded.asof_utc,
            stale_days=excluded.stale_days,
            y3m=excluded.y3m,
            y2y=excluded.y2y,
            y5y=excluded.y5y,
            y10y=excluded.y10y,
            y30y=excluded.y30y,
            spread_2y10y_bp=excluded.spread_2y10y_bp,
            spread_3m10y_bp=excluded.spread_3m10y_bp,
            curve_shape=excluded.curve_shape,
            validation_json=excluded.validation_json,
            raw_json=excluded.raw_json,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            payload["observation_date"],
            payload["source_primary"],
            payload.get("source_secondary"),
            payload["quality"],
            payload["asof_utc"],
            payload["stale_days"],
            r.get("3M"),
            r.get("2Y"),
            r.get("5Y"),
            r.get("10Y"),
            r.get("30Y"),
            payload["spread_2y10y_bp"],
            payload["spread_3m10y_bp"],
            payload["curve_shape"],
            json.dumps(payload.get("validation") or {}, ensure_ascii=False),
            json.dumps(payload, ensure_ascii=False),
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill official rates history")
    parser.add_argument("--days", type=int, default=365, help="lookback days (default 365)")
    args = parser.parse_args()

    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=max(1, args.days))

    fred = {tenor: fetch_fred_series(sid) for tenor, sid in FRED_SERIES.items()}
    required = ["3M", "2Y", "10Y"]
    common = set(fred[required[0]].keys())
    for tenor in required[1:]:
        common &= set(fred[tenor].keys())

    # full curve preferred when possible
    full_curve_dates = set(fred["3M"].keys())
    for tenor in ["2Y", "5Y", "10Y", "30Y"]:
        full_curve_dates &= set(fred[tenor].keys())

    chosen_dates = sorted(d for d in full_curve_dates if datetime.strptime(d, "%Y-%m-%d").date() >= start_date)
    if not chosen_dates:
        print("no dates available in lookback window")
        return 1

    treasury = fetch_treasury_history(start_year=start_date.year, end_year=today.year)

    asof_utc = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        ensure_schema(conn)

        inserted = 0
        for d in chosen_dates:
            rates = {tenor: round(float(fred[tenor][d]), 3) for tenor in ["3M", "2Y", "5Y", "10Y", "30Y"] if d in fred[tenor]}
            if "2Y" not in rates or "10Y" not in rates or "3M" not in rates:
                continue

            spread_2y10y_bp = round((rates["10Y"] - rates["2Y"]) * 100, 1)
            spread_3m10y_bp = round((rates["10Y"] - rates["3M"]) * 100, 1)

            validation = {
                "matched_date": False,
                "treasury_observation_date": None,
                "diff_2y_bp": None,
                "diff_10y_bp": None,
                "max_abs_diff_bp": None,
            }
            tr = treasury.get(d)
            if tr is not None:
                validation["matched_date"] = True
                validation["treasury_observation_date"] = d
                diff_2y = round((rates["2Y"] - tr.get("2Y", rates["2Y"])) * 100, 1) if tr.get("2Y") is not None else None
                diff_10y = round((rates["10Y"] - tr.get("10Y", rates["10Y"])) * 100, 1) if tr.get("10Y") is not None else None
                validation["diff_2y_bp"] = diff_2y
                validation["diff_10y_bp"] = diff_10y
                diffs = [abs(v) for v in (diff_2y, diff_10y) if v is not None]
                validation["max_abs_diff_bp"] = max(diffs) if diffs else None

            stale_days = (today - datetime.strptime(d, "%Y-%m-%d").date()).days
            payload = {
                "observation_date": d,
                "source_primary": "fred",
                "source_secondary": "treasury" if tr else None,
                "quality": "official",
                "asof_utc": asof_utc,
                "stale_days": stale_days,
                "rates": rates,
                "spread_2y10y_bp": spread_2y10y_bp,
                "spread_3m10y_bp": spread_3m10y_bp,
                "curve_shape": curve_shape(spread_3m10y_bp),
                "validation": validation,
            }
            upsert_row(conn, payload)
            inserted += 1

        row = conn.execute(
            "SELECT COUNT(*), MIN(observation_date), MAX(observation_date) FROM yield_curve_daily"
        ).fetchone()

    print(f"backfill_inserted_or_updated={inserted}")
    print(f"db_total_rows={row[0]} range={row[1]}~{row[2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
